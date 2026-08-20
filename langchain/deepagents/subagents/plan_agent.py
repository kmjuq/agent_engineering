"""Plan 模式：基于 deepagents 的规划型多子代理协作框架。

核心思想
--------
一个 *主管 (Planner)* agent 负责拆解用户目标并制定分步计划，
随后通过 deepagents 内置的 `task` 工具把每个子任务派发给专用的
*subagent*（研究员 / 写作者 / 编码者）。每个 subagent 在隔离的上下文
窗口中自主完成任务，只把最终结果回传给主管，最后由主管汇总成统一答复。

这种「先规划、再派发」的模式适合：
- 目标明确但步骤繁多的复杂任务；
- 子任务彼此独立、可并行处理；
- 需要把思考链与执行链分离，避免主线程上下文被中间过程污染。

依赖
----
    from deepagents import create_deep_agent, SubAgent

    agent = build_plan_agent(model=...)
    agent.invoke({"messages": [{"role": "user", "content": "<你的目标>"}]},
                  config={"configurable": {"thread_id": "1"}})
"""

from __future__ import annotations

from typing import Any

from deepagents import SubAgent, create_deep_agent
from deepagents.backends.protocol import BackendProtocol
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver


# ---------------------------------------------------------------------------
# 主管 (Planner) 系统提示
# ---------------------------------------------------------------------------
PLANNER_SYSTEM_PROMPT = """你是一个「规划型主管 (Planner)」。

你的职责不是亲自执行任务的细枝末节，而是：
1. 理解用户的最终目标；
2. 把目标拆解成一组**相互独立、可并行**的子任务；
3. 为每个子任务调用 `task` 工具，把它派发给最合适的专用 subagent；
4. 收集所有 subagent 的返回结果，综合成一份清晰、完整的答复。

## 工作流程
1. 先输出一份简要的「执行计划」清单（用编号列出子任务），让用户看清思路。
2. 当多个子任务之间没有依赖关系时，**在同一条消息里并行发起多个 `task` 调用**，
   以节省等待时间。
3. 若某个子任务依赖另一个子任务的结果，则必须等待前者完成后再发起。
4. 每个 `task` 调用的 `description` 必须包含：
   - 子任务的明确目标；
   - 完成任务所需的全部上下文；
   - 期望返回结果的格式（例如「返回要点列表」「返回可直接运行的代码」）。
5. 所有 subagent 返回后，用你自己的话总结，而不是原样粘贴 subagent 输出。

## 注意事项
- 普通、简单的任务（几步以内）不要强行拆分，直接处理即可。
- 如果任务目标含糊，先提出最关键的一个澄清问题，再开始规划。
- 你无法直接看到 subagent 的中间过程，只能看到它的最终汇报，因此派发时要写清要求。
"""

# ---------------------------------------------------------------------------
# 专用 subagent 提示词
# ---------------------------------------------------------------------------
RESEARCHER_PROMPT = """你是一名研究员 subagent。

你会收到一条独立的调研任务。请使用可用工具（搜索、读文件、glob、grep 等）
收集信息，并在最终消息中给出结构化结论。

输出要求：
- 先用一两句话说明调研范围；
- 再用要点列出关键发现（每条附带来源或依据）；
- 最后给出一句总结性判断。
只输出最终调研报告，不要描述你的思考过程。
"""

WRITER_PROMPT = """你是一名写作者 subagent。

你会收到一段明确的写作需求（主题、体裁、篇幅、要点、受众等）。
请直接产出成稿内容，并遵循以下要求：

- 紧扣需求，不跑题；
- 结构清晰，使用标题、列表等组织内容；
- 默认使用 Markdown 格式；
- 只输出最终稿件，不要附带「以下是为你准备的…」之类的客套话。
"""

CODER_PROMPT = """你是一名编码者 subagent。

你会收到一个明确的编程 / 自动化任务。请使用文件系统与执行工具完成任务，
并在最终消息中汇报：

- 你创建或修改的文件路径；
- 关键代码或核心逻辑的简要说明；
- 运行结果或验证方式（若适用）。

若任务只需给出代码而非真正执行，请直接输出带语言标注的代码块。
只输出最终结果，不要复述你的调试过程。
"""

GENERALIST_PROMPT = """你是一名通用 subagent。

你会收到一个相对独立、需要多步骤处理的子任务。请自主使用可用工具完成它，
并在最终消息中返回该子任务的完整结果。

- 调用方（主管）只能看到你的最终消息，看不到中间过程，因此请把结论写全；
- 若任务需要产出文件，请明确写出文件路径；
- 不要询问主管，按你的最佳判断推进，遇到阻塞再说明卡点。
"""


def build_subagents(model: BaseChatModel | str) -> list[SubAgent]:
    """构造 plan 模式下使用的专用 subagent 列表。

    返回一个 `SubAgent` 字典列表，可直接传给 `create_deep_agent(subagents=...)`。
    注意：deepagents 在未提供 `general-purpose` 时会自动注入一个通用 subagent，
    这里仍显式声明一个，便于定制提示词。

    Args:
        model: 子代理使用的模型（与主代理一致或更强）。
    """
    return [
        {
            "name": "researcher",
            "description": (
                "研究员：负责资料检索、信息收集与事实核查。"
                "适合需要先查清楚背景、数据、文档再下结论的子任务。"
            ),
            "system_prompt": RESEARCHER_PROMPT,
            "model": model,
            "tools": [],
        },
        {
            "name": "writer",
            "description": (
                "写作者：负责撰写报告、文章、说明文档、邮件等成稿内容。"
                "适合纯文本产出类子任务。"
            ),
            "system_prompt": WRITER_PROMPT,
            "model": model,
            "tools": [],
        },
        {
            "name": "coder",
            "description": (
                "编码者：负责写代码、改文件、跑脚本、做数据处理等工程类子任务。"
                "适合需要操作文件系统或执行命令的子任务。"
            ),
            "system_prompt": CODER_PROMPT,
            "model": model,
            "tools": [],
        },
        {
            "name": "generalist",
            "description": (
                "通用执行者：处理不适合上述专门分类、但仍可独立完成的子任务。"
            ),
            "system_prompt": GENERALIST_PROMPT,
            "model": model,
            "tools": [],
        },
    ]


def build_plan_agent(
    model: BaseChatModel | str,
    *,
    backend: BackendProtocol | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    extra_tools: list[Any] | None = None,
    subagents: list[SubAgent] | None = None,
) -> Any:
    """构建一个 plan 模式的 deep agent。

    该 agent 由一个 Planner 主管 + 多个专用 subagent 组成。主管优先做规划，
    再通过 `task` 工具把子任务派发给 subagent 并行/串行执行。

    Args:
        model: 主 agent 与 subagent 使用的模型。
        backend: 文件后端（如 `StateBackend()` / `FilesystemBackend(...)`）。
        checkpointer: 状态检查点（多轮对话 / 中断需要）。
        extra_tools: 额外工具（会同时继承给未单独声明 tools 的 subagent）。
        subagents: 自定义 subagent 列表；缺省使用 `build_subagents` 提供的默认集。

    Returns:
        编译好的 deep agent（可直接 `.invoke(...)`）。
    """
    agent = create_deep_agent(
        model=model,
        tools=extra_tools or [],
        system_prompt=PLANNER_SYSTEM_PROMPT,
        subagents=subagents if subagents is not None else build_subagents(model),
        backend=backend,
        checkpointer=checkpointer,
    )
    return agent


# ---------------------------------------------------------------------------
# 便捷运行入口（脚本 / Notebook 均可调用）
# ---------------------------------------------------------------------------
def run_plan(agent: Any, goal: str, thread_id: str = "plan-1") -> str:
    """运行一次 plan 任务并返回主管的最终答复文本。"""
    result = agent.invoke(
        {"messages": [{"role": "user", "content": goal}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content


if __name__ == "__main__":
    import os
    import sys

    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    from utils.std_model import base_model

    plan_agent = build_plan_agent(base_model())
    answer = run_plan(
        plan_agent,
        "帮我调研 deepagents 的 plan 模式，写一份 300 字的中文简介，"
        "并给出一段最小可运行的 Python 示例代码片段。",
    )
    print(answer)
