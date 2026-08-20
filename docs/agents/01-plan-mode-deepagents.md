# 01 · 基于 deepagents 的 Plan 模式（多 SubAgent 协作）

> 对应实现：`langchain/deepagents/subagents/plan_agent.py` 与 `plan_mode.ipynb`
> 关键词：deepagents / Plan Mode / SubAgent / task 工具 / 规划-派发

## 1. 背景与动机

复杂任务往往「目标清晰、步骤繁多、各步骤可独立」。若让单个 agent 串行完成，
存在两个问题：

1. **上下文污染**：调研、草稿、调试等中间过程挤占主线程窗口，导致后期遗忘早期约束。
2. **无法并行**：彼此无关的子任务被迫排队，拖慢整体时延。

Plan 模式借鉴「规划-派发」思想：由一个**主管 (Planner)** 先做拆解，
再通过 deepagents 内置的 `task` 工具，把子任务交给**专用 subagent** 在隔离上下文里处理，
最后汇总。这与 Anthropic / OpenAI 提出的 plan-mode、orchestrator-worker 模式一脉相承。

## 2. 整体架构

```
            ┌────────────────────────────┐
   用户目标 →│  Planner 主管 (create_deep_agent) │
            └──────────────┬─────────────┘
                           │ 制定分步计划，调用 task 工具
              ┌────────────┼────────────┬────────────┐
              ▼            ▼            ▼            ▼
        researcher     writer       coder      generalist
       (调研/检索)   (写作/成稿)  (编码/文件)  (通用执行)
              └────────────┴────────────┴────────────┘
                           │ 各自返回最终结论（无中间过程）
                           ▼
                   Planner 汇总 → 统一答复
```

要点：
- Planner 本身通过 `create_deep_agent(subagents=[...])` 注册子代理；
- deepagents 自动为 Planner 注入 `task` 工具，调用时参数 `subagent` 指定目标子代理；
- subagent 在**独立上下文窗口**运行，主管只能看到其最终消息，看不到中间链路；
- 无依赖的子任务应在**同一条消息里并行发起多个 `task` 调用**。

## 3. 核心 API 用法

```python
from deepagents import create_deep_agent, SubAgent
from utils.std_model import base_model

subagents = [
    {
        "name": "researcher",
        "description": "研究员：资料检索与事实核查",
        "system_prompt": RESEARCHER_PROMPT,
        "model": base_model(),
        "tools": [],   # 继承主代理工具，或在此单独声明
    },
    # writer / coder / generalist 同上
]

agent = create_deep_agent(
    model=base_model(),
    system_prompt=PLANNER_SYSTEM_PROMPT,
    subagents=subagents,
)
```

`SubAgent` 字段：
- `name`：派发时 `task` 的 `subagent` 取值；
- `description`：告诉主管何时该选这个子代理（影响路由准确性，务必写清职责边界）；
- `system_prompt`：**每个 subagent 独立的系统提示**，是隔离上下文的关键；
- `model`：可各自指定强弱不同的模型；
- `tools`：可覆盖继承的工具集。

> 注意：deepagents 在未显式提供 `general-purpose` 时会自动注入一个通用 subagent；
> 本实现显式声明 `generalist` 以便定制提示词。

## 4. 派发策略（Planner 决策逻辑）

| 情形 | 派发方式 | 示例 |
| --- | --- | --- |
| 子任务相互独立 | **单条消息并行**多个 `task` | 调研 + 写作 + 代码三段无依赖 |
| 子任务 B 依赖 A 结果 | 先发 A，收到回报后**再发 B** | 先调研 RAG，再据结论写摘要 |
| 目标含糊 | 先向用户提 1 个关键澄清问题 | 范围 / 受众 / 格式未定 |
| 简单任务（≤3 步） | 不拆分，直接处理 | 一句话翻译、简单问答 |

Planner 的 system prompt 强制要求：派发时写清「目标 + 必要上下文 + 期望返回格式」，
因为 subagent 看不到对话历史，只依赖该次 `task` 描述。

## 5. 文件清单

| 文件 | 作用 |
| --- | --- |
| `plan_agent.py` | 核心实现：`PLANNER_SYSTEM_PROMPT`、各 subagent 提示词、`build_subagents`、`build_plan_agent`、`run_plan` |
| `plan_mode.ipynb` | 可直接运行的 Notebook：协作型 / 依赖型 / 自定义 subagent 三类示例 |

## 6. 运行方式

```bash
# 作为脚本
python langchain/deepagents/subagents/plan_agent.py

# 或 Notebook
jupyter notebook langchain/deepagents/subagents/plan_mode.ipynb
```

环境变量（API Key）由 `utils.env.auto_load_env` 自动加载，与仓库其他 notebook 一致。

## 7. 可扩展方向

- **动态规划**：让 Planner 先产出 JSON 计划，由外层控制循环逐条派发并支持中途人工确认（HITL）。
- **专用工具**：为 coder 单独挂载文件系统/执行类工具，为 researcher 挂载搜索工具。
- **质量门禁**：subagent 返回后由 Planner 做一次「是否满足派发要求」的校验，不满足则重新派发。
- **成本控制**：高并发 subagent 使用更便宜的小模型，Planner 用强模型做决策。
