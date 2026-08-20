# 阶段四：智能体化 RAG（Agentic RAG）

> 这是与你的 **AI Agent** 学习最直接相关的阶段。模块化 RAG 仍是"静态图"——流程部署时就定死了。智能体化 RAG 则让 **LLM Agent 在运行时自主决策**：何时检索、检索什么、检索几次、调用什么工具、何时停止。RAG 从"管道"升级为"会思考的工作流"。

---

## 目录

1. [从 RAG 到 Agentic RAG](#一从-rag-到-agentic-rag)
2. [Agentic RAG 的核心能力](#二agentic-rag-的核心能力)
3. [三种典型架构模式](#三三种典型架构模式)
4. [工具调用（Tool Use）与多源检索](#四工具调用tool-use与多源检索)
5. [代表工作：Self-RAG 与 CRAG](#五代表工作self-rag-与-crag)
6. [用 LangGraph 构建 Agentic RAG（实战思路）](#六用-langgraph-构建-agentic-rag实战思路)
7. [多智能体协作 RAG](#七多智能体协作-rag)
8. [收益、成本与治理](#八收益成本与治理)

---

## 一、从 RAG 到 Agentic RAG

回顾前几个阶段的根本限制：

- **基础/进阶/模块化 RAG**：检索的"时机与方式"是**人预先设计好**的（上来就检索一次、固定流程）。
- **问题**：很多真实问题并不适合"一次性检索"：
  - 需要先想清楚"我要查什么"再查（规划）；
  - 查一次不够，要基于结果决定"还要不要继续查"（迭代）；
  - 查到的内容不可靠，需要换思路重查（纠错）；
  - 不同子问题要调不同工具/数据源（路由）。

**Agentic RAG 的解法**：把检索本身交给 **Agent（智能体）** 来驱动。Agent 借助 LLM 的推理能力，在循环中**观察（Observation）→ 思考（Thought）→ 行动（Action）**，其中"行动"可以是"再检索一次""换个查询""调用某个 API""停止并回答"。

```
        ┌──────────────────────────────────────┐
        │              Agent (LLM)              │
        │  思考：我还需要查 X / 已够 / 不可靠     │
        └───────┬───────────┬───────────┬───────┘
                │检索        │调用工具    │回答
                ▼            ▼            ▼
         向量库/知识库   搜索引擎/API   最终答案
          (可多轮)      (计算器/DB)
                └────────────┴────────────┘
                    结果反馈给 Agent 再决策（循环）
```

---

## 二、Agentic RAG 的核心能力

| 能力 | 说明 | 解决什么 |
| --- | --- | --- |
| **决策是否检索** | 简单问题可不检索直接答，复杂问题才检索 | 省成本、降噪 |
| **规划检索步骤** | 把复杂问题拆成有序的子检索计划 | 多跳/复杂问题 |
| **迭代检索** | 基于上一轮结果决定继续检索 | 信息不足时自动补检 |
| **自我纠错** | 判断检索结果是否可靠，不可靠则换策略 | 召回噪声/无关 |
| **工具调用** | 检索之外还能搜网页、算数、查数据库 | 多源异构信息 |
| **反思终止** | 判断是否已充分，决定停止并作答 | 防止无限循环/过度检索 |

---

## 三、三种典型架构模式

### 3.1 路由式（Router）

- **做法**：Agent 先判断问题类型，再路由到对应检索器/知识源。
- **示例**：`代码问题 → 代码库检索`；`政策问题 → 制度文档检索`；`实时数据 → 数据库/API`。
- **对应**：模块化 RAG 的"分支"被 Agent 动态决定。

### 3.2 迭代式 / 自我纠错（Iterative & Corrective）

- **做法**：检索 → 评估相关性 → 不足则改写查询再检索，形成循环，直到满意或达步数上限。
- **代表**：**CRAG（Corrective RAG）**、Self-RAG 的迭代检索。
- **价值**：显著提升"难问题"的命中率。

### 3.3 多步规划式（Plan-and-Solve）

- **做法**：先制定检索计划（拆子问题），逐步执行并汇总。
- **代表**：Step-Back、Plan-and-Solve、RAPTOR 的 Agent 化。
- **价值**：适合研究型、跨文档综合问答。

---

## 四、工具调用（Tool Use）与多源检索

Agentic RAG 把"检索"泛化为"任意工具调用"，使 RAG 从单一向量库扩展到**多工具生态**：

| 工具类型 | 例子 | 用途 |
| --- | --- | --- |
| 向量检索 | FAISS/Milvus 查询 | 语义知识召回 |
| 关键词检索 | Elasticsearch/BM25 | 精确术语召回 |
| 网页搜索 | Bing/SerpAPI | 实时外部信息 |
| 结构化查询 | SQL / 知识图谱 | 数值、关系数据 |
| 计算 | Python/Calculator | 推理与计算 |
| API | 内部系统接口 | 业务数据 |

> Agent 依据问题自主选择工具组合（如"先用 SQL 取销售额，再用向量库找对应财报段落，最后生成分析"），这是纯 RAG 管道做不到的。

---

## 五、代表工作：Self-RAG 与 CRAG

### 5.1 Self-RAG（Self-Reflective Retrieval-Augmented Generation, 2023）

- **来源**：Akari Asai et al., University of Washington。
- **核心**：训练一个会**自我反思**的模型，在生成过程中动态插入特殊标记决策：
  - `Retrieve`：是否需要检索？
  - `IsRel`：检索到的段落是否相关？
  - `IsSup`：生成内容是否有证据支持（faithfulness）？
  - `IsUse`：该段落是否有助于回答？
- **机制**：模型边生成边判断，需要时才检索、并评估证据质量，不可靠就丢弃或再检索。
- **价值**：在**忠实度（减少幻觉）**与**灵活性**上明显优于传统 RAG；把"检索决策"内化进生成过程。
- **工程启示**：即便不重训模型，也可用 LLM + 提示词实现"轻量版 Self-RAG"（用 Critic 提示判断是否相关/充分）。

### 5.2 CRAG（Corrective RAG, 2024）

- **来源**：Yan et al., 2024。
- **核心**：用一个**轻量检索评测器（T5 自评器）**对每次检索结果打分：
  - **Correct** → 直接用；
  - **Incorrect** → 触发**网页检索（Web Search）**兜底；
  - **Ambiguous** → 结合两者。
- **价值**：给 RAG 加了"纠错保险"——知识库不足时自动转向外部搜索，鲁棒性强。
- **工程启示**：非常适合"私有库 + 公网兜底"的混合场景。

---

## 六、用 LangGraph 构建 Agentic RAG（实战思路）

LangGraph 用「**状态图（StateGraph）**」编排 Agent 循环，非常契合 Agentic RAG。一个最小范式：

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END

class State(TypedDict):
    question: str
    query: str
    docs: list            # 累积检索到的文档
    attempts: int
    answer: str

# 节点函数（伪代码）
def rewrite(state):       # 改写查询
    state["query"] = llm_rewrite(state["question"])
    return state

def retrieve(state):      # 检索
    state["docs"] += vectorstore.search(state["query"], k=3)
    state["attempts"] += 1
    return state

def critique(state):      # 评估是否充分
    return "ok" if llm_judge(state["question"], state["docs"]) else "retry"

def generate(state):      # 生成答案
    state["answer"] = llm_generate(state["question"], state["docs"])
    return state

# 编排
g = StateGraph(State)
g.add_node("rewrite", rewrite)
g.add_node("retrieve", retrieve)
g.add_node("generate", generate)
g.add_edge("rewrite", "retrieve")
g.add_conditional_edges("retrieve", critique,   # 条件路由
                        {"ok": "generate", "retry": "rewrite"})
g.add_edge("generate", END)
```

**关键设计点：**
- **State** 保存累积的 `docs` 与 `attempts`，支持多轮检索。
- **条件边（conditional_edges）** 实现"充分则生成、不足则改写重查"的自我纠错。
- 可在此基础上加 `web_search` 节点（实现 CRAG 式兜底）、加 `router` 节点（实现路由式）。

> 本仓库 `langchain/langgraph.ipynb` 与 `deepagents/` 提供了可直接运行的 Agent 编排示例，建议配合动手。

---

## 七、多智能体协作 RAG（Multi-Agent RAG）

当任务更大时，可由**多个专职 Agent** 分工协作：

- **检索 Agent**：负责找资料；
- **分析 Agent**：负责提炼与推理；
- **批判 Agent**：负责校验证据与事实一致性；
- **编写 Agent**：负责产出最终答案。

它们通过消息传递协作（如 `langgraph` 的 `Send` / `multi-agent` 模式）。适合**大型研究、报告生成、跨领域综合**任务。

---

## 八、收益、成本与治理

### 收益
- 准确率高、鲁棒性强，能处理传统 RAG 做不到的复杂/多跳/开放式问题。
- 检索更"按需"，常能减少无谓检索。

### 成本与风险
- **延迟与费用上升**：多轮 LLM 调用、多工具调用。
- **可能无限循环**：需设 `max_attempts`、超时与降级策略。
- **可控性下降**：自主决策带来结果不确定性，需**日志/可观测性**（追踪每步检索与决策）。
- **评测更重要**：见 [05-前沿与趋势.md](./05-前沿与趋势.md) 的 RAGAS 评测。

### 治理建议
- 明确"何时用 Agentic RAG、何时用简单管道"（按问题复杂度路由）。
- 每次检索/工具调用都记录（便于审计与 Debug）。
- 设置步数上限、相关性阈值、失败兜底（如转人工/转网页搜索）。

---

→ 下一篇：[05-前沿与趋势.md](./05-前沿与趋势.md)（GraphRAG、多模态、评测等）
