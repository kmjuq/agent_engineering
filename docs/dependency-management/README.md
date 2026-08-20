# 依赖管理（dependency-management）

本话题记录本仓库 Python 依赖管理的方案、决策与结论，重点是 **macOS Intel (x86_64) 与 Apple Silicon (arm64) 双平台可执行**。

## 文档列表

- [01-macos双平台依赖处理.md](./01-macos双平台依赖处理.md)：macOS 双平台（Intel/ARM）依赖兼容性处理的完整过程与结论

## 相关话题

- [rag/](../rag/)：RAG 相关包（milvus、llama-index、faiss 等）已从硬依赖移除，如未来需要本地 embedding / 向量检索，参照本话题的决策重新引入
- [agents/](../agents/)：agent 相关依赖（deepagents、langchain、tavily 等）为当前保留的核心依赖
