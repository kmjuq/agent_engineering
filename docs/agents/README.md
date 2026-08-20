# agents/ 话题索引

本目录沉淀与 **AI Agent / 多智能体协作** 相关的讨论、设计与实现。

## 文档清单

| 文档 | 说明 |
| --- | --- |
| [01-plan-mode-deepagents.md](./01-plan-mode-deepagents.md) | 基于 deepagents 的 Plan 模式：Planner 主管 + 专用 subagent 协作拆分与执行复杂任务 |
| [02-codebuddy-agent-loop-deepagents.md](./02-codebuddy-agent-loop-deepagents.md) | CodeBuddy 风格 Agent Loop：有边界的局部控制合同（local_aim/action/evaluator/budget/escalation）+ 双层架构 |
| [03-todolist-middleware.md](./03-todolist-middleware.md) | langchain `TodoListMiddleware` 的计划处理机制：`write_todos` 工具注入 / system prompt 追加 / `Command(update={"todos": ...})` 状态更新 / 如何在 v3 流中观察计划过程 |
| [04-ai-agent产品工程发展趋向.md](./04-ai-agent产品工程发展趋向.md) | AI Agent 产品工程发展趋向调研：生态格局、架构演进、八大工程趋向（协议标准化/可控自主/评估驱动/可靠性/记忆/Agentic RAG/安全治理/成本平台化）、产品形态与落地方向 |

## 约定

- 所有结论先落盘于此，再在对话中给出摘要（详见仓库根 `AGENTS.md`）。
- 修订已有结论采用增量更新，并标注修改点。
