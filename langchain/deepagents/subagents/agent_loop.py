"""CodeBuddy 风格的 Agent Loop Demo（基于 deepagents）。

设计来源
--------
参考 CodeBuddy / Addy Osmani 提出的 **Loop Engineering** 范式：把 Coding Agent
的内部循环设计成一份「有边界的局部控制合同」，而非随意重试。本合同包含五个
关键构件：

    local_aim   局部目标   —— 循环被允许收敛的问题范围，生命周期内不变
    action      行动策略   —— 每次迭代派 agent 行动一步（手段可变，目标不可变）
    evaluator   评测器     —— 唯一有资格宣布「成功」的角色（也可触发升级）
    budget      预算       —— 最大迭代次数，耗尽即停止（budget_exhausted）
    escalation  升级       —— 越权 / 目标冲突时交人工，不自扩权

层次划分（双层架构）
--------------------
- **Loop 层**：本文件 `AgentLoop` 类，负责单目标的局部收敛，返回结构化结果。
- **Graph 层**：`run_graph()` 调度函数，决定跑哪个 loop、如何处理其 handoff
  （success → 结束；budget_exhausted / escalated → 升级给人工或下游）。

运行
----
    python langchain/deepagents/subagents/agent_loop.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# 把仓库根目录加入 path，便于 `from utils.std_model import base_model`
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from langchain_core.language_models import BaseChatModel  # noqa: E402

from utils.std_model import base_model  # noqa: E402


# ---------------------------------------------------------------------------
# 结构化结果（Loop 的诚实停止信号）
# ---------------------------------------------------------------------------
class LoopStatus(str, Enum):
    SUCCESS = "success"          # 评测器裁定通过
    BUDGET_EXHAUSTED = "budget_exhausted"  # 预算耗尽仍未通过
    ESCALATED = "escalated"      # 越权 / 目标冲突，升级给人工


@dataclass
class LoopResult:
    status: LoopStatus
    iterations: int
    history: list[dict] = field(default_factory=list)  # 每轮 [(action, verdict, reason)]
    final_output: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "iterations": self.iterations,
            "final_output": self.final_output,
            "history": self.history,
        }


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------
ACTION_SYSTEM_PROMPT = """你是一个「行动 agent」，在一个受控的循环里逐步完成任务。

规则：
- 你只负责**一步**行动：根据当前目标和上一轮评测反馈，产出这一轮应交付的内容
  （例如代码、修改、回答）。不要试图一次做完所有事，循环会带你迭代。
- 如果评测反馈指出了问题，请针对性地修正，不要重复之前的错误。
- 只输出这一轮的行动结果本身，不要把思考过程也写进去。
- 你**不能**改变任务的最终目标，只能调整实现手段。
"""

EVALUATOR_SYSTEM_PROMPT = """你是一个「评测器 (evaluator)」，是本轮循环里**唯一**有资格宣布
任务成功的角色。你需要判断行动 agent 的产出是否已经满足目标。

收到：(1) 目标；(2) 行动 agent 的产出；(3) 必要的客观验证信息（如测试结果）。

判定规则：
- 若产出已完全满足目标 → 返回 verdict=pass，并简述理由。
- 若产出未满足目标 → 返回 verdict=fail，并给出**具体、可操作的**下一步修正建议
  （告诉行动 agent 该改哪里）。
- 若你发现任务目标本身含糊、冲突，或行动 agent 需要超出权限才能继续
  （例如要求执行危险命令、修改无关系统）→ 返回 verdict=escalate，说明理由。

只输出如下 JSON，不要多余文字：
{"verdict": "pass" | "fail" | "escalate", "reason": "<一句话理由>"}
"""


# ---------------------------------------------------------------------------
# Agent Loop 控制器（Loop 层）
# ---------------------------------------------------------------------------
class AgentLoop:
    """一个 CodeBuddy 风格的 agent loop。

    Args:
        local_aim: 局部目标（生命周期内不变）。
        model: 行动 / 评测使用的模型。
        action_tools: 行动 agent 可使用的工具（如搜索、文件、执行）。
        verifier: 可选的外部验证函数（如跑测试），返回 (passed: bool, info: str)。
                  提供时评测器会拿到客观信息，否则仅做语义判定。
        budget: 最大迭代次数。
    """

    def __init__(
        self,
        local_aim: str,
        model: BaseChatModel,
        *,
        action_tools: list | None = None,
        verifier: Callable[[str], tuple[bool, str]] | None = None,
        budget: int = 3,
    ) -> None:
        self.local_aim = local_aim
        self.budget = budget
        self.verifier = verifier

        # 行动 agent（内层 worker）
        from deepagents import create_deep_agent

        self.action_agent = create_deep_agent(
            model=model,
            tools=action_tools or [],
            system_prompt=ACTION_SYSTEM_PROMPT,
        )
        # 评测器复用同一模型，但走纯 LLM 调用（轻量、结构化）
        self.evaluator_llm = model

    # ---- 单步：行动 ----
    def _act(self, feedback: str | None) -> str:
        msg = f"目标：{self.local_aim}"
        if feedback:
            msg += f"\n\n上一轮评测反馈（请据此修正）：{feedback}"
        out = self.action_agent.invoke(
            {"messages": [{"role": "user", "content": msg}]}
        )
        return out["messages"][-1].content

    # ---- 单步：评测 ----
    def _evaluate(self, action_output: str) -> dict:
        verification_info = ""
        if self.verifier is not None:
            try:
                passed, info = self.verifier(action_output)
                verification_info = (
                    f"\n\n客观验证结果：{'通过' if passed else '未通过'}，详情：{info}"
                )
            except Exception as exc:  # 验证本身出错也算未通过，附上错误
                verification_info = f"\n\n客观验证出错：{exc}"

        prompt = (
            f"目标：{self.local_aim}\n\n"
            f"行动 agent 产出：\n{action_output}"
            f"{verification_info}\n\n请按评测器规则输出 JSON 判定。"
        )
        resp = self.evaluator_llm.invoke(
            [
                {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        # 容错解析 JSON
        text = resp.content
        match = re.search(r"\{.*\}", text, re.DOTALL)
        try:
            return json.loads(match.group(0)) if match else {"verdict": "fail", "reason": text}
        except json.JSONDecodeError:
            return {"verdict": "fail", "reason": text}

    # ---- 主循环 ----
    def run(self) -> LoopResult:
        feedback: str | None = None
        history: list[dict] = []

        for i in range(1, self.budget + 1):
            action_output = self._act(feedback)
            verdict = self._evaluate(action_output)
            v = verdict.get("verdict", "fail")
            reason = verdict.get("reason", "")

            if v == "escalate":
                history.append({"iter": i, "verdict": v, "reason": reason})
                return LoopResult(
                    status=LoopStatus.ESCALATED,
                    iterations=i,
                    history=history,
                    final_output=action_output,
                )

            history.append({"iter": i, "verdict": v, "reason": reason})

            if v == "pass":
                return LoopResult(
                    status=LoopStatus.SUCCESS,
                    iterations=i,
                    history=history,
                    final_output=action_output,
                )

            # fail → 把理由作为下一轮反馈（预算耗尽则停止）
            feedback = reason

        return LoopResult(
            status=LoopStatus.BUDGET_EXHAUSTED,
            iterations=self.budget,
            history=history,
            final_output=action_output,
        )


# ---------------------------------------------------------------------------
# Graph 层：调度 + 升级处理
# ---------------------------------------------------------------------------
def run_graph(aim: str, model: BaseChatModel, **loop_kwargs) -> dict:
    """运行一个 agent loop 并处理其 handoff（Graph 层的职责）。"""
    loop = AgentLoop(aim, model, **loop_kwargs)
    result = loop.run()

    if result.status == LoopStatus.SUCCESS:
        decision = "已完成，无需人工介入。"
    elif result.status == LoopStatus.BUDGET_EXHAUSTED:
        decision = "预算耗尽仍未通过：升级给人工审查最后产出。"
    else:  # escalated
        decision = "触发升级：目标含糊/越权，交由人工裁决。"

    return {**result.to_dict(), "graph_decision": decision}


# ---------------------------------------------------------------------------
# 示例：自带客观验证器（跑一段 Python 代码）
# ---------------------------------------------------------------------------
def _extract_code(text: str) -> str | None:
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1) if m else None


def python_code_verifier(output: str) -> tuple[bool, str]:
    """把 agent 产出的代码写到临时文件并执行，检查是否能正确运行且含 fib 函数。"""
    code = _extract_code(output)
    if not code:
        return False, "未检测到代码块"
    if "def fib" not in code:
        return False, "缺少 fib 函数定义"

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code + "\n\nprint('FIB10=', fib(10))\n")
        path = f.name
    try:
        import subprocess

        proc = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            return False, f"运行报错: {proc.stderr[-300:]}"
        return True, proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "执行超时"
    finally:
        os.unlink(path)


if __name__ == "__main__":
    llm = base_model()

    aim = (
        "写一个 Python 函数 fib(n)，返回斐波那契数列第 n 项（n 从 0 开始，"
        "fib(0)=0, fib(1)=1）。要求函数名为 fib，并能正确计算 fib(10)。"
    )

    print("=" * 60)
    print("CodeBuddy 风格 Agent Loop Demo")
    print("局部目标:", aim)
    print("=" * 60)

    result = run_graph(
        aim,
        llm,
        verifier=python_code_verifier,  # 客观验证：真正执行代码
        budget=3,
    )

    print("\n--- Loop 历史 ---")
    for h in result["history"]:
        print(f"  第 {h['iter']} 轮: {h['verdict']} — {h['reason']}")
    print(f"\n最终状态: {result['status']}")
    print(f"Graph 决策: {result['graph_decision']}")
    print("\n--- 最终产出 ---")
    print(result["final_output"])
