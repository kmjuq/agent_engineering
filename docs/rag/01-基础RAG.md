# 阶段一：基础 RAG（Naive RAG）

> 基础 RAG 确立了 RAG 最经典的「**索引（Indexing）→ 检索（Retrieval）→ 生成（Generation）**」三段式线性管道，是整个技术体系的基石。理解每个环节的实现细节与局限，才能理解后续所有优化为何存在。

---

## 目录

1. [整体管道回顾](#一整体管道回顾)
2. [环节一：索引（Indexing）](#二环节一索引indexing)
3. [环节二：检索（Retrieval）](#三环节二检索retrieval)
4. [环节三：生成（Generation）](#四环节三生成generation)
5. [基础 RAG 的核心痛点](#五基础-rag-的核心痛点)
6. [最小可运行示例思路](#六最小可运行示例思路)

---

## 一、整体管道回顾

```
                  离线（Offline）                 在线（Online）
┌──────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│ 原始文档  │───►│ 1.加载 2.清洗 3.分块   │    │ 用户提问              │
│ (PDF/网页 │    │ 4.Embedding 5.入库    │    │    │                  │
│  /数据库) │    │        ↓             │    │    ▼                  │
└──────────┘    │  向量数据库           │    │ 向量化Query → 相似检索 │
                └──────────────────────┘    │    │                  │
                                            │    ▼                  │
                                            │ 拼接 Prompt → LLM 生成 │
                                            │    │                  │
                                            │    ▼                  │
                                            │   带引用答案            │
                                            └──────────────────────┘
```

基础 RAG 的工作分为**离线建库**与**在线问答**两条路径，下面逐一拆解。

---

## 二、环节一：索引（Indexing）

索引是把「人类可读文档」变成「机器可检索向量」的过程，决定了后续检索的天花板。

### 2.1 文档加载（Loading）

- **目标**：把不同格式的源数据读入统一文本表示。
- **常见格式**：PDF、Word、Markdown、HTML、纯文本、数据库表、API 返回、Confluence / Notion 等。
- **要点**：保留**结构信息**（标题层级、表格、页码），结构越完整，后续分块越合理。
- **工具**：LangChain `Document Loaders`、LlamaIndex `Reader`、Unstructured、pdfplumber。

### 2.2 清洗与预处理（Cleaning）

- 去除页眉页脚、导航栏、重复空白、乱码。
- 统一编码、修复断句、处理表格为文本（或保留为 Markdown 表格）。
- 对代码、公式等特殊内容做保留处理（不强行分词破坏语义）。

### 2.3 分块（Chunking）—— 最关键也最易被忽视的一步

分块是把长文档切分为若干「片段（chunk）」，每个 chunk 单独向量化、单独被检索。

**为什么必须分块？**
- LLM 上下文窗口有限，无法一次塞入整本书。
- 检索粒度越细，召回越精准（避免把无关内容也塞进上下文）。

**常见分块策略：**

| 策略 | 做法 | 优点 | 缺点 |
| --- | --- | --- | --- |
| 固定长度切分 | 按字符/Token 数（如 500 token）硬切 | 简单、均匀 | 切断语义（句子/段落被劈开） |
| 按分隔符切分 | 优先在段落/句号处切 | 比硬切自然 | 仍可能不完美 |
| 递归字符切分 | 按 `\n\n` → `\n` → `.` 递归尝试 | LangChain 默认，较均衡 | 仍可能割裂 |
| 语义分块 | 用 embedding 相似度找边界 | 语义完整 | 计算成本高（见进阶 RAG） |
| 按结构切分 | 按 Markdown 标题层级 | 保留结构 | 依赖源格式规范 |

**关键参数：**
- **chunk size（块大小）**：太大→噪声多、检索不精；太小→语义不完整、跨块信息丢失。
- **chunk overlap（重叠）**：相邻块重叠一部分（如 50 token），缓解边界割裂。**推荐设置 10%~20% 重叠**。

> ⚠️ 基础 RAG 最常用的就是「固定长度 / 递归字符分块」，这是后续所有分块优化的起点。

### 2.4 向量化（Embedding）

- **目标**：把文本 chunk 映射为固定维度的稠密向量（如 768 / 1536 维）。
- **原理**：Embedding 模型（双塔/Transformer）把语义相近的文本映射到向量空间中相近的位置。
- **常见模型**：OpenAI `text-embedding-3`、BGE-M3、E5、Cohere Embed、Jina Embeddings。
- **注意**：查询（query）和文档（chunk）必须用**同一个 Embedding 模型**向量化，否则空间不一致无法比较。

### 2.5 入库（Vector Store）

- 把 `(chunk文本, 向量, 元数据)` 写入向量数据库。
- **元数据**：来源文件名、页码、标题、时间等，可用于后续过滤。
- **常见向量库**：FAISS（本地轻量）、Chroma（易上手）、Milvus / Qdrant / Weaviate（生产级）、pgvector（PostgreSQL 扩展）。

---

## 三、环节二：检索（Retrieval）

用户提问时，把问题向量化，并在向量库中找最相似的 chunk。

### 3.1 查询向量化

用与建库**相同**的 Embedding 模型对用户问题做向量化。

### 3.2 相似度度量（Similarity Metric）

| 度量 | 公式思想 | 说明 |
| --- | --- | --- |
| **余弦相似度（Cosine）** | 向量夹角余弦 | 最常用，只关心方向忽略模长 |
| **点积（Dot Product）** | 向量内积 | 当向量已归一化时等价于余弦 |
| **欧氏距离（L2）** | 向量空间距离 | 距离越小越相似 |

> 工程上通常对向量做归一化后使用**点积/余弦**，多数向量库默认余弦。

### 3.3 Top-K 召回

- 取相似度最高的 K 个 chunk（如 K=3~5）作为候选上下文。
- K 太小→可能漏掉关键信息；K 太大→噪声多、超出上下文窗口、稀释注意力。
- 基础 RAG 通常直接把 Top-K 全部喂给 LLM（**无重排序**，这是主要短板）。

### 3.4 检索的「朴素」之处

基础 RAG 的检索是**单轮、无改写、无重排、无过滤**的：问题什么样就直接拿去检索。这在问题表述与文档用词不一致、或问题复杂时，召回质量较差。

---

## 四、环节三：生成（Generation）

把检索到的上下文与问题拼成 Prompt，交给 LLM 生成答案。

### 4.1 上下文拼接（Prompt Assembly）

典型模板：

```
请仅根据以下【参考资料】回答问题。如果资料中没有答案，请回答"我不知道"。

【参考资料】
{chunk_1}
{chunk_2}
{chunk_3}

【问题】
{user_question}

【回答】
```

### 4.2 关键工程要点

- **指令约束**：明确要求「基于资料回答」「不编造」「资料不足时说不知道」，可显著降低幻觉。
- **引用来源**：要求模型在答案中标注引用（如 `[1]`），便于溯源与可信度建设。
- **上下文顺序**：把最关键/最相关的 chunk 放在靠前位置（位置偏差：LLM 对开头/结尾更敏感）。

### 4.3 生成阶段的局限

- 若检索阶段召回的是噪声，生成阶段只能「一本正经地基于错误信息回答」（垃圾进、垃圾出）。
- 多个 chunk 之间可能矛盾或冗余，基础 RAG 不会做去重/压缩。

---

## 五、基础 RAG 的核心痛点

理解这些痛点，是学习进阶 RAG 的「动机清单」：

1. **召回率低 / 召回噪声大**：问题表述与文档用词不一致时检索失败；Top-K 无筛选混入噪声。
2. **分块割裂语义**：硬切分块破坏句子/段落完整性，关键信息被拆散到不同 chunk。
3. **长文档信息分散**：答案需要跨多个 chunk 甚至跨文档拼接，单次检索难以覆盖。
4. **缺乏查询理解**：用户问题含糊、口语化、含歧义，直接检索效果差。
5. **无法应对复杂/多跳问题**：需要多次检索、推理的问题，单轮管道无能为力。
6. **上下文冗余与溢出**：chunk 过多导致超出上下文、注意力被稀释。

> 进阶 RAG（见 [02-进阶RAG.md](./02-进阶RAG.md)）正是围绕「检索前 / 检索中 / 检索后」三个环节逐一解决上述痛点。

---

## 六、最小可运行示例思路

伪代码（以 LangChain + FAISS 为例）：

```python
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# ---- 离线索引 ----
docs = load_and_split("knowledge.pdf")          # 加载 + 递归分块
embeddings = OpenAIEmbeddings()
vectorstore = FAISS.from_documents(docs, embeddings)
vectorstore.save_local("faiss_index")

# ---- 在线检索 + 生成 ----
vs = FAISS.load_local("faiss_index", embeddings)
retrieved = vs.similarity_search(question, k=3)  # Top-K 检索

prompt = ChatPromptTemplate.from_template(
    "根据资料回答问题，资料不足时说不知道。\n资料：{ctx}\n问题：{q}"
)
ctx = "\n".join(d.page_content for d in retrieved)
answer = ChatOpenAI().invoke(prompt.format(ctx=ctx, q=question))
```

> 这正是「基础 RAG」的全部：它简单、可跑通，但离生产级准确率还差一截——下一阶段见分晓。

---

→ 下一篇：[02-进阶RAG.md](./02-进阶RAG.md)（检索全链路优化）
