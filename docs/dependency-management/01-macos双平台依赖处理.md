# macOS 双平台依赖处理（Intel / ARM）

> 更新记录：2026-08-20 初稿（依赖清理与双平台验证完成）

## 背景与目标

本仓库的 Python 工程（`uv` 管理，`requires-python = ">=3.14"`）需要在 **macOS Intel (x86_64)** 与 **macOS Apple Silicon (arm64)** 两台机器上都能正常解析、安装与执行。

原始 `pyproject.toml` 依赖了大量 AI 生态包，其中部分包在 macOS 双平台上的可用性存在差异，导致 Intel 机器无法安装。

## 一、基础配置：限定解析平台

在 `pyproject.toml` 中加入：

```toml
[tool.uv]
environments = [
  "sys_platform == 'darwin' and platform_machine == 'arm64'",
  "sys_platform == 'darwin' and platform_machine == 'x86_64'",
]
```

作用：`uv lock` 只为 macOS 双架构做通用解析，生成的 `uv.lock` 中 `resolution-markers` 只包含这两个平台；不再为 Windows / Linux 拉取无关包（如 `pywin32`、`secretstorage`、nvidia CUDA 系、`triton` 等被自动移除）。

## 二、核心矛盾：torch 在 Intel Mac 上无可用 wheel

`uv lock` 后解析出的 `torch==2.13.0` 只有 `macosx_14_0_arm64` wheel，**没有 macOS x86_64 wheel**，Intel 机器上 `uv sync` 直接失败。

事实核查（PyPI 索引）：

- torch 2.3.0 起**停止发布 macOS x86_64 wheel**；
- 最后一个支持 Intel Mac 的版本是 **2.2.2**（`macosx_10_9_x86_64`）；
- 但项目要求 Python >= 3.14，而 torch 2.2.2 不支持 Python 3.14（其 wheel 最高到 cp312）。

结论：**在 Python 3.14 约束下，torch 系依赖不可能在 macOS 双平台同时可用**，必须从硬依赖中移除，而不是"同时支持"。

## 三、决策演进：从"可选依赖 + 动态导入"到"直接删除"

### 方案 A：optional-dependencies + 动态导入（已尝试，未采用）

将 `llama-index-embeddings-huggingface` / `sentence-transformers` 挪到 `[project.optional-dependencies]`，代码中 `try/except ImportError` 动态导入并降级。

**结论**：动态导入只能解决"运行时缺库"，解决不了 `uv sync` 安装阶段的失败；且当时 `unstructured[md,pdf]` → `unstructured-inference` → `torch` 仍是硬依赖链，无法规避。用户选择直接删除不用的包。

### 方案 B：直接删除引入 torch 的包（最终采用）

删除清单（均确认代码中无实际引用）：

| 包 | 引入 torch 的路径 | 原因 |
| --- | --- | --- |
| `unstructured[md,pdf]` | → `unstructured-inference` → `torch` | RAG 文档解析用，代码已删 |
| `langchain-unstructured` | → `unstructured`（同上） | RAG 文档解析用 |
| `sentence-transformers` | → `torch` | 本地 embedding，代码已删 |
| `llama-index-embeddings-huggingface` | → `sentence-transformers` → `torch` | 本地 embedding |

注意：`langchain-huggingface` **不**引入 torch，已保留（HF 模型 API 集成）。

### 方案 C：删除 RAG 相关包（用户追加要求）

`rag/` 目录的 notebook 中 embedding / 向量检索使用代码已删除，继续删除：

- `langchain-milvus`（向量库）
- `llama-index`、`llama-index-llms-openai-like`（RAG 框架）
- `langchain-text-splitters`（splitters）

保留：`langchain-tavily` / `tavily-python` —— `langchain/deepagents.ipynb` 仍将 Tavily 作为 agent 搜索工具使用（`utils/std_tavily.py`），不属于 RAG 专用。

## 四、faiss-cpu 版本收敛

删除 RAG 包后，`llama-index-core` 曾引入的 `faiss-cpu` 也随之移除。但此前单独验证过该包的双平台 wheel 覆盖情况，记录如下（未来若重新引入向量检索可参考）：

| 版本 | arm64 wheel | x86_64 wheel |
| --- | --- | --- |
| 1.15.0 / 1.14.3 | `macosx_14_0_arm64` | `macosx_15_0_x86_64`（仅 macOS 15） |
| 1.13.2 | `macosx_14_0_arm64` | `macosx_14_0_x86_64` |
| **1.12.0** | `macosx_14_0_arm64` | `macosx_13_0_x86_64`（macOS 13+，最宽） |

结论：如需要，`faiss-cpu<1.13.0` 覆盖 macOS 13+ 双平台，是兼容性最优的 pin。

## 五、最终 pyproject.toml（依赖部分）

```toml
dependencies = [
  "deepagents>=0.5.1",
  "fastmcp>=3.2.4",
  "langchain>=1.2.15",
  "langchain-daytona>=0.0.7",
  "langchain-deepseek>=1.0.1",
  "langchain-huggingface>=1.2.2",
  "langchain-mcp-adapters>=0.2.2",
  "langchain-openai>=1.1.12",
  "langchain-quickjs>=0.1.2",
  "langchain-tavily>=0.2.17",
  "langgraph>=1.1.6",
  "notebook>=7.5.5",
  "openai>=2.41.0",
  "requests>=2.34.2",
  "tavily-python>=0.7.24",
]
```

## 六、验证结果

- `uv lock`：解析 **262 个包**（清理前 334），torch 系全部移除（torch/torchvision/sentence-transformers/unstructured-inference/accelerate/timm/unstructured 均为 0 残留）；
- `uv sync --dry-run --python-platform aarch64-apple-darwin`：通过；
- `uv sync --dry-run --python-platform x86_64-apple-darwin`：通过；
- 本机（macOS x86_64, Python 3.14）实际 `uv sync`：成功；`import langchain, langgraph, deepagents, langchain_openai, langchain_tavily` 全部通过。

## 七、后续注意事项

1. **不要重新引入 torch 系依赖**（Python 3.14 约束下双平台不可兼得）。如需本地 embedding，建议改用 API embedding（OpenAI / DeepSeek / Tavily 等），或仅在 ARM 机器上按需 `uv sync --extra`（如未来恢复 optional-dependencies 方案）。
2. 新增依赖时建议用 `uv sync --dry-run --python-platform aarch64-apple-darwin` 与 `x86_64-apple-darwin` 双平台预检，避免回归。
3. 两个平台可共用同一个 `uv.lock`（已做通用解析），无需各自 lock。
