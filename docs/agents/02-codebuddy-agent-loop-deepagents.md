# 02 · 用 deepagents 实现 CodeBuddy 风格的 Agent Loop

> 对应实现：`langchain/deepagents/subagents/agent_loop.py` 与 `agent_loop.ipynb`
> 关键词：CodeBuddy / Loop Engineering / Agent Loop / Evaluator / Budget / Escalation / deepagents

## 1. Agent Loop 是什么（设计范式）

CodeBuddy 的 agent loop 遵循 **Loop Engineering**（Addy Osmani，2026）范式：
开发者不应一轮轮手动 Prompt Agent，而应设计一个**循环系统**去自动 Prompt Agent。
核心是把循环设计成一份「**有边界的局部控制合同**」，关键词 **局部、评价、停止、升级**。

对比其他工程范式：

| 范式 | 解决什么 |
| --- | --- |
| Prompt Engineering | 怎么把一句话说清楚 |
| Context / Harness Engineering | Agent 该看什么、单次长任务如何稳定完成 |
| **Loop Engineering** | 系统持续运转：何时启动、谁验收、能否续跑（AI 时代的 CI/CD）|

## 2. 合同的五个关键构件

| 构件 | 含义 | 本 demo 对应 |
| --- | --- | --- |
| `local_aim` 局部目标 | 循环被允许收敛的问题范围，生命周期内不变 | `AgentLoop.local_aim` |
| `action` 行动策略 | 每次迭代派 agent 行动一步；手段可变，**目标不可变** | `AgentLoop._act()` |
| `evaluator` 评测器 | 唯一有资格宣布「成功」的角色；也可触发升级 | `AgentLoop._evaluate()` |
| `budget` 预算 | 最大迭代次数，耗尽即停止（诚实信号） | `AgentLoop.budget` |
| `escalation` 升级 | 越权 / 目标冲突 → 交人工，不自扩权 | verdict=`escalate` |

结构化 handoff（`LoopStatus`）：`success` / `budget_exhausted` / `escalated` —— 后两者是**诚实停止信号**，而非假装完成。

## 3. 双层架构

```
        ┌──────────────────────────────┐
 Graph  │  run_graph() 调度与 handoff   │
 层     │  成功→结束 / 失败·升级→人工    │
        └──────────────┬───────────────┘
                       │ 启动一个 loop
        ┌──────────────▼───────────────┐
 Loop   │  AgentLoop（单目标局部收敛）   │
 层     │  迭代: act → evaluate → 判定   │
        │  预算耗尽 / 升级 → 返回 handoff │
        └──────────────────────────────┘
```

- **Loop 层**只管局部收敛，返回结构化结果；不知道全局目标如何拆分。
- **Graph 层**（`run_graph`）负责路由下游、处理跨 loop 依赖、把 `budget_exhausted`/`escalated` 升级给人工或编排器（`graph_governor`）。

## 4. 为什么用 deepagents

- **内层行动 agent**：用 `create_deep_agent` 创建，可挂载工具（搜索、文件、执行），天然支持多步工具调用。
- **评测器**：轻量 LLM 调用（不必构建完整 agent），强制输出 `{"verdict","reason"}` JSON，作为唯一成功裁定者。
- **客观验证器（可选）**：`verifier` 回调让评测器拿到 ground truth（如本 demo 真正执行生成的 Python 代码），避免纯语义判定的不可靠。

> 注：当前安装的 deepagents 版本**没有**官方 `plan_mode` 参数（详见 `01-plan-mode-deepagents.md`）。本 demo 的 loop 控制完全由外层 Python 实现，deepagents 仅作内层 worker，因此不受该限制影响。

## 5. 核心代码骨架

```python
class AgentLoop:
    def __init__(self, local_aim, model, *, action_tools=None,
                 verifier=None, budget=3): ...
    def _act(self, feedback) -> str:          # 行动 agent 走一步
    def _evaluate(self, output) -> dict:      # 评测器判定 pass/fail/escalate
    def run(self) -> LoopResult:              # 主循环，预算耗尽停止

def run_graph(aim, model, **kw) -> dict:      # Graph 层调度 + handoff
```

客观验证器示例（执行生成的代码）：

```python
def python_code_verifier(output):
    code = _extract_code(output)              # 取 ```python 代码块
    # 写临时文件 → subprocess 执行 → 返回 (passed, info)
```

## 6. 运行与示例

```bash
python langchain/deepagents/subagents/agent_loop.py
# 或 jupyter notebook langchain/deepagents/subagents/agent_loop.ipynb
```

示例场景：让 agent 写 `fib(n)` 并验证 `fib(10)==55`。第一轮即 `pass`，验证器真实执行代码确认。
把 `budget` 设为 1 并给复杂任务，可观察 `budget_exhausted` 的诚实停止。

## 7. 设计要点与陷阱

- **Loop 会放大错误**：手动 Prompt 错一轮，Loop 可能连续错。必须有预算上限 + 客观验证器 + 沙箱。
- **评测器是唯一成功裁定者**：不要把「是否完成」的判定权下放给行动 agent 自己。
- **越权即升级**：行动 agent 想改目标 / 做危险操作 → `escalate`，Loop 不自扩权；仅靠 system prompt 写「勿做危险操作」不够，需权限控制。
- **状态文件续跑**：生产级 Loop 应把 `history` 落盘，次日从断点续跑（本 demo 未含，可扩展）。

## 8. 与 Plan 模式（01）的关系

- `01-plan-mode` 是 **Planner + 固定 subagent 派发**，强调「先规划、子任务隔离」。
- 本 `agent_loop` 是 **单目标迭代收敛**，强调「预算、评测、升级」的闭环治理。
- 二者可组合：Planner 拆出子目标 → 每个子目标跑一个 `AgentLoop` → Graph 层汇总。
