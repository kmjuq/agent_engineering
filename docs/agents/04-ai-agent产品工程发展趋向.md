# AI Agent 产品的工程发展趋向调研

> 调研时间：2026-08-20
> 方法：基于公开资料与行业实践的综合性梳理（部分内容经由 DeepSeek agent 实测调研产出，见 `03-todolist-middleware.md` 的 agent 运行记录）
> 范围：聚焦"工程"维度（架构、开发范式、可靠性、可观测性、安全、成本、平台化），不深入模型算法本身

## 目录

1. [格局：四层生态](#一格局四层生态)
2. [架构演进：三个时代](#二架构演进三个时代)
3. [核心工程趋向（重点）](#三核心工程趋向重点)
4. [产品形态与落地趋向](#四产品形态与落地趋向)
5. [总结：五条主线](#五总结五条主线)
6. [给工程团队的建议](#六给工程团队的建议)
7. [相关链接](#七相关链接)

---

## 一、格局：四层生态

当前可观察到的 Agent 产品大致分四层：

| 层次 | 代表产品/项目 | 工程重点 |
| --- | --- | --- |
| 模型层 | GPT-5/o 系列、Claude、Gemini、DeepSeek | 函数调用、Agentic 训练（工具使用 RL）、长上下文 |
| 框架/SDK 层 | LangChain/LangGraph、CrewAI、AutoGen、OpenAI Agents SDK、Google ADK、Claude Agent SDK、smolagents、MetaGPT、Pydantic AI、DSPy | 编排、状态机、多智能体、可观测性 |
| 运行时/基础设施层 | MCP 生态、E2B/Daytona 沙箱、模型网关（LiteLLM）、LangSmith/Langfuse 观测、向量库（Milvus/Pinecone/Qdrant）、记忆中间件（Mem0/Zep/Letta） | 协议、沙箱、观测、安全、记忆 |
| 产品/应用层 | ChatGPT Operator、Claude Code、Cursor、Devin、GitHub Copilot、Manus、AutoGLM、企业 Copilot 平台 | 人机协同、垂类落地、商业化 |

**结论先行**：Agent 工程正从"框架竞赛"转向 **"协议 + 运行时 + 评测 + 护栏"四件套的标准化竞赛**；产品形态从"全自主大而全"收敛到"可控的、可评测的、垂类的数字员工"。

---

## 二、架构演进：三个时代

1. **提示词时代（2022–2023）**：单一 LLM + prompt，Agent 是"套壳对话"。
2. **框架时代（2023–2024）**：AutoGPT/BabyAGI 引发热炒，LangChain 等框架主导；特点是"自由 Agent"，但不可控、不可评测、成本爆炸——这是后来被系统性批判的教训。
3. **工程化时代（2024 至今）**：收敛到 Anthropic 提出的 **workflow vs agent 二元论**——能用确定性流程解决的不用 Agent，Agent 只用在真正需要动态决策的地方。主流架构变成 **"工作流骨架 + Agent 决策点 + 工具 + 记忆 + 人工确认"** 的混合体。

核心架构模式（已成为业界通用语言）：
- 确定性工作流：提示链（prompt chaining）、路由（routing）、并行化（parallelization）
- 半自主：编排器-执行者（orchestrator-workers）、评估-优化（evaluator-optimizer）
- 全自主：ReAct 循环 + 规划 + 反思（reflection）

---

## 三、核心工程趋向（重点）

### 趋向 1：协议标准化——"Agent 的 HTTP 时刻"

2024 下半年以来最重要的信号：

- **MCP（Model Context Protocol，Anthropic 发起）**：把"工具、数据源、能力"做成标准化 server，Agent 通过统一协议消费。已被 OpenAI、Google、Microsoft、AWS 等竞对共同接纳，成为事实标准。工程含义：**工具与 Agent 解耦**——工具侧只写一次 MCP server 即可被所有 Agent 复用；出现 MCP 注册中心/网关（Smithery、各家 marketplace）。
- **A2A（Agent2Agent，Google 发起）**：Agent 之间的互通协议，2025 年捐给 Linux 基金会；配套 **AG-UI**（人机交互协议）与 **Agent Card**（能力描述/发现）。方向是"Agent 网络"而非单一 Agent。
- **观测标准化**：OpenTelemetry GenAI 语义约定，把 LLM 调用、工具调用、检索纳入统一可观测标准。

> 工程影响：接 Agent 不再等于"换框架"，而是"实现协议"。协议层会像 HTTP/TCP 一样沉淀为长期资产。

### 趋向 2：从"全自主"到"可控自主"（human-in-the-loop）

早期 AutoGPT 式"让 Agent 自己跑完"被证伪，产品全面转向**确认点（approval gate）**设计：

- Operator / computer use 类产品：敏感操作（支付、提交、发布）必须人工确认。
- Claude Code / Cursor 等编码 Agent：文件修改、命令执行都需审阅；发展出"只读探索模式"与"执行模式"分离。
- 工程上沉淀出：**权限最小化、操作分级（只读/写/破坏性）、会话内审批流、审计日志、信任分级（trust tiering，低风险自动 / 高风险确认）**。

> 这是"Agent 产品化"与"Agent 演示"最重要的分水岭。

### 趋向 3：开发范式工程化——从"提示词工程"到"评估驱动开发"

- **Agent as Code / Config**：提示词、工具定义、模型选择、编排图全部可版本化、可评审、可回滚，纳入 Git 流程。
- **评估成为一等公民（Eval-driven development）**：先建评测集、再迭代。手段包括轨迹评测（trajectory eval）、LLM-as-judge、沙箱任务模拟器（SWE-bench、τ-bench、Terminal-Bench、WebArena、OSWorld、GAIA）。
- **CI/CD for Agents**：提示词/工具变更走流水线、灰度发布、A/B 与金丝雀；"无评测不上线"成为社区共识。
- **Tracing 成为标配**：LangSmith、Langfuse、Phoenix、W&B Weave 提供全链路 trace，Agent 每一步决策、工具调用、token 消耗都可回溯。

> 注意：当前仓库的 `docker-compose.yml` 已包含 Langfuse，与本仓库的 agent 工程化实践方向一致（观测基础设施）。

### 趋向 4：可靠性工程——弹性、状态与护栏

- **弹性**：重试、超时、幂等、指数退避——传统分布式系统经验被系统性搬进 agent 运行时。
- **状态持久化与断点续跑（durable execution）**：检查点（checkpointing）、断点续跑、会话外部化，是长任务可靠性的根基（LangGraph checkpointing、Claude Code 会话恢复、Azure Agent Service 会话管理）。可类比 Temporal 模式。
- **护栏（Guardrails）**：输出校验、策略约束（NeMo Guardrails、Guardrails AI）、预算/步数上限（如 langchain 的 `ToolCallLimitMiddleware` / `ModelCallLimitMiddleware`）。
- **成熟度模型**：行业开始用类似自动驾驶 L0–L5 / CMMI 的分级描述 agent 自主度，多数产品目前处于"受控自主（L1–L2）"。

### 趋向 5：记忆与上下文工程——从"单次提示"到"分层记忆"

- **上下文压缩**：长上下文虽在扩展，但成本与延迟倒逼工程侧做滑动窗口、摘要/压缩、分块检索。
- **记忆分层**：工作记忆（会话内）→ 情景记忆 → 语义记忆 → 程序记忆；出现 Mem0、Zep、Letta（MemGPT）、LangMem 等记忆中间件，配套遗忘与合并策略。
- **状态外部化**：会话与记忆从模型上下文剥离，存进外部存储，支持跨会话、跨实例复用。
- **Context Engineering（上下文工程）**被提为与 Prompt Engineering 并列的独立工程学科：系统化组织、注入、裁剪上下文，管理上下文预算（token 预算）、缓存与检索优先级。

### 趋向 6：知识接入——从 RAG 到 Agentic RAG

- 第一代 RAG（向量检索 + 拼接）正在升级为 **Agentic RAG**：由 Agent 自主决定"何时检索、检索什么、多步迭代检索、检索结果如何验证"。
- 工程配套：混合检索（关键词+向量）、重排序、引文溯源、检索质量评估，以及知识库与 Agent 记忆的融合。
- 与本仓库的关联：RAG 相关依赖此前已从项目剥离（见 `dependency-management/`），本仓库当前 Agent 的"知识"来源是工具调用（Tavily 搜索、文件系统）而非本地向量库。

### 趋向 7：安全、治理与 HITL

- **Prompt Injection 防护**：Agent 读取网页、邮件、文档等外部内容，注入攻击成为头号安全议题；威胁模型从"直接注入"扩展到"间接注入（经工具/网页数据）"、工具滥用、权限逃逸、数据泄漏。OWASP 已发布 Agentic AI 十大威胁清单。
- **权限与沙箱**：最小权限原则、敏感操作审批流、容器/虚拟机隔离（E2B、Daytona、WASM）、审计日志、可随时中止（kill switch）。
- **合规与治理**：EU AI Act 一般用途 AI 义务落地；企业侧要求"可解释、可审计、可回滚"，agent 身份与既有 IAM（SSO/RBAC）打通。

### 趋向 8：基础设施、成本与模型策略

- **托管运行时与 Agent 云**：OpenAI AgentKit/Responses API、各类 agent-as-a-service 把"推理 + 工具 + 记忆 + 编排"打包成托管服务，降低自建成本。
- **成本优化成为工程议题**：小模型/大模型路由、模型蒸馏、专属微调、prompt caching、结果缓存、流式与预测性执行。Agent 类产品的 token 消耗远高于聊天，成本工程直接决定商业模式能否成立。
- **低代码平台与云厂商一体化**：Dify、Coze（扣子）、FastGPT、RAGFlow 降低交付门槛；AWS AgentCore、Azure AI Foundry Agent Service、Vertex AI Agent Engine 提供"运行时 + 目录 + 运维 + 治理"一体化平台，对标"云原生之于微服务"。

---

## 四、产品形态与落地趋向

| 方向 | 代表产品/形态 | 工程特点 |
| --- | --- | --- |
| 编程智能体 | Claude Code、Devin、Cursor、Copilot Agent | 沙箱执行、测试驱动验证、与 IDE/Git 深度集成 |
| 浏览器/任务智能体 | OpenAI Operator、Deep Research、Manus | 屏幕理解、长任务规划、网络操作沙箱 |
| 企业 Copilot 平台 | Microsoft Copilot Studio、Salesforce Agentforce、ServiceNow | 低代码编排、企业数据连接器、治理与审批 |
| 垂直领域 Agent | 金融、法律、医疗、客服 | 领域知识库 + 合规审计 + 人机协同 |
| 开源框架 | LangGraph、CrewAI、AutoGen、smolagents、HF 生态 | 从"重框架抽象"回归"轻量、透明、可控" |

**框架演化值得单独强调**：行业经历了"LangChain 全家桶（抽象过重）→ LangGraph（图编排）→ 原生 SDK（OpenAI Agents SDK、直接调 API + 自写状态机）"的轮回。趋势是**减少魔法、增加透明度和可调试性**，很多团队甚至回归"模型 API + 结构化工具定义 + 自己的编排循环"。

**风险提示**：Gartner 预计相当比例的 agentic AI 项目将在 2027 年前被取消（价值不清、成本高、治理不足）——"Demo 惊艳、生产翻车"是当前最大行业风险；"先确定性工作流、后自主 agent"是共识路线。

---

## 五、总结：五条主线

1. **标准化**：MCP / A2A / Function Calling / Agent Skills 让 Agent 生态从"孤岛"走向"互操作"，接入层和技能市场是新的工程机会点。
2. **可靠性工程化**：评估、tracing、回归、沙箱、HITL 把 Agent 从"演示品"推向"可运维的生产系统"——这是当前最大的工程缺口，也是最大的机会。
3. **从"多 Agent"回归"务实架构"**：Workflow 与 Agent 分层，单 Agent + 强工具 + 好编排是主流，多 Agent 用于并行与校验。
4. **记忆与上下文成为一等公民**：上下文工程、记忆分层、Agentic RAG 决定 Agent 的"聪明程度"和成本。
5. **安全与成本决定规模化**：注入防护、权限治理、模型路由与缓存，是 Agent 能否在企业真实环境中大规模部署的前提。

---

## 六、给工程团队的建议

- 先建"评估 + tracing"地基再上 Agent 功能，避免后期返工。
- 优先采用 MCP 等开放协议做工具接入，保持可组合性和生态红利。
- 用"确定性 Workflow 兜底 + Agent 处理例外"的混合架构控制风险和成本。
- 用信任分级（HITL）渐进扩大自主度：从单一高价值场景切入，先做受控自主。
- 任何 Agent 都必须回答"价值、成本、治理"三问，警惕演示效应。

---

## 七、相关链接

- [03-todolist-middleware.md](./03-todolist-middleware.md)：TodoList 计划机制（本调研曾作为 agent 实测任务运行，含完整运行记录）
- [01-plan-mode-deepagents.md](./01-plan-mode-deepagents.md)：deepagents Plan 模式
- [02-codebuddy-agent-loop-deepagents.md](./02-codebuddy-agent-loop-deepagents.md)：Agent Loop 双层架构
- [../dependency-management/](../dependency-management/)：本仓库依赖清理决策（RAG 包剥离等）
