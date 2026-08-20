# DeepSeek 使用自身模型的联网搜索（Web Search）

> 结论时间：2026-08-20。信息基于 DeepSeek 官方文档与 2026-08-01 的 Responses API 实测（见文末来源）。

## 目录

1. [结论速览](#一结论速览)
2. [路径一：官方网页版 / App（零代码）](#二路径一官方网页版--app零代码)
3. [路径二：Responses API 原生服务端搜索（推荐给开发者）](#三路径二responses-api-原生服务端搜索推荐给开发者)
4. [路径三：Anthropic 兼容端点 + web_search_20250305 工具](#四路径三anthropic-兼容端点--web_search_20250305-工具)
5. [路径四：DeepSeek Harness / Agent 生态](#五路径四deepseek-harness--agent-生态)
6. [常见误区与选型建议](#六常见误区与选型建议)

## 一、结论速览

"DeepSeek 使用它自己大模型的 websearch" 有以下四种形态，按接入成本从低到高：

| 路径 | 适用人群 | 是否"自带" | 核心要点 |
| --- | --- | --- | --- |
| ① 官方网页版 / App | 普通用户 | ✅ 内置 | 聊天框勾选「联网搜索」按钮即可 |
| ② Responses API 服务端搜索 | 开发者 | ✅ 内置 | `tools: [{"type": "web_search"}]`，黑盒注入，约 0.2~1 分/次 |
| ③ Anthropic 兼容端点工具 | 开发者（Agent 生态） | ✅ 内置 | `/anthropic` 端点复用 `web_search_20250305` 工具，自带来源列表 |
| ④ Harness / Agent 工具 | Agent 框架开发者 | ✅ 内置 | 面向 Claude Code / Copilot / OpenCode 等工具的开发者预览 |

> **关键限制**：DeepSeek 的**服务端原生搜索只在 `responses` 端点可用**；`chat/completions` 端点传 `web_search` 工具会被 400 拒绝（2026-08-01 实测）。网页版的能力 ≠ chat/completions 的能力，需要联网的 API 场景请走 Responses API 或 Anthropic 兼容端点。

## 二、路径一：官方网页版 / App（零代码）

- 打开 [chat.deepseek.com](https://chat.deepseek.com) 或 DeepSeek App。
- 在输入框区域找到「联网搜索」开关（默认关闭，V4 网页版为图形化按钮）。
- 打开后提问，模型会在回答前自动检索实时网页内容。
- 适用：日常使用、验证需求、产品体验。不适合程序化调用。

## 三、路径二：Responses API 原生服务端搜索（推荐给开发者）

### 3.1 调用方式

- 端点：`https://api.deepseek.com/responses`（Responses API，OpenAI 兼容格式）
- 在请求 `tools` 中声明 `{"type": "web_search"}`，`tool_choice` 默认 `auto`，模型自主决定是否搜索。

请求示例：

```json
{
  "model": "deepseek-v4-flash",
  "input": "今天北京天气怎么样？",
  "tools": [{"type": "web_search"}],
  "stream": false
}
```

### 3.2 黑盒机制（重要）

服务端搜索是「黑盒注入」——搜索结果只注入给 LLM 上下文，**客户端 API 拿不到结果列表**：

| 数据 | 能否获取 |
| --- | --- |
| 搜索结果内容（标题+摘要+正文） | ❌ 拿不到（直接注入上下文） |
| 引用 URL | ⚠️ 仅 `open_page` 动作暴露；`search` 动作只有 `queries` 无 URL |
| 搜索词 `queries` | ✅ 有（需过滤 `ws_call_id=call_xx` 追踪尾巴） |
| 最终回答 | ✅ `message.output_text` |

响应中 `web_search_call` item 只有 `action` 字段，两种形态：

| 形态 | 字段 | 含义 |
| --- | --- | --- |
| `search` 动作 | `queries: [...]` | 只有搜索词，无 URL |
| `open_page` 动作 | `url: "https://..."` | 模型主动决定打开的页面，无 title |

### 3.3 流式事件时序（stream: true）

无 `[DONE]`，以 `RESPONSE.COMPLETED` 收尾：

```
response.output_item.added           → web_search_call item（in_progress）
response.web_search_call.in_progress → 只有 item_id
response.web_search_call.searching   → 只有 item_id
response.web_search_call.completed   → 只有 item_id，action=null
response.output_item.done            → 完整 item 带 action（queries 或 url 在这里）
```

> **坑**：`completed` 事件里 `action=null`，URL 要到 `output_item.done` 才出现。前端若在 completed 就渲染会闪「未找到来源」——应保持「搜索中」占位，等 `output_item.done` 聚合后一次性渲染。

### 3.4 成本（DeepSeek-V4-Flash，元/百万 tokens）

| 计费项 | 单价 |
| --- | --- |
| 输入（缓存命中） | 0.02 元/百万（便宜 50 倍） |
| 输入（缓存未命中） | 1 元/百万 |
| 输出 | 2 元/百万 |

- 单次联网搜索约 **0.2~1 分钱**（冷启动 0.4~1 分；热缓存后低至 0.2~0.3 分）。
- 成本大头是「缓存未命中的输入」：一次搜索注入约 7K~17K tokens。
- 实测缓存命中率约 59%，多轮对话/重复搜索越来越便宜。
- 注意：官方预告北京时间 9:00~12:00、14:00~18:00 高峰时段价格 ×2。

### 3.5 给 Agent 开发者的建议

1. 能接受来源不可见 → 直接用服务端搜索，集成成本为零。
2. 需要 Perplexity 式完整引用列表 → 服务端搜索不够，需自接搜索 API（Tavily/Serper）或对 `open_page` URL 抓标题。
3. 流式渲染等 `output_item.done`，别在 `completed` 渲染。
4. 剥掉 `ws_call_id=` / `#ws_call_id=` 尾巴。
5. 省 token：instructions 里引导「搜索后最多打开 1 个最相关页面」。
6. 前端要展示引用时引导 `open_page` 2~4 个页面；不需要时 1 个或纯搜索即可。

## 四、路径三：Anthropic 兼容端点 + web_search_20250305 工具

DeepSeek 提供 Anthropic 兼容端点，可复用 Anthropic 定义的 `web_search_20250305` 工具，**用 DeepSeek 自己的 API Key** 即可联网，无需申请第三方搜索 API：

- 端点：`https://api.deepseek.com/anthropic`（`/v1/messages`）
- 工具名：`web_search_20250305`
- 返回：模型综合的回答 + 来源列表（网页标题、链接、页面日期）

Node.js 示例（deepseek-kit 封装后的用法，底层即上述端点）：

```ts
import { createAgent, createModel, webSearch } from 'deepseek-kit'

const model = createModel({ model: 'deepseek-v4-flash' })
const agent = createAgent({ model, tools: [webSearch()] })

const result = await agent.generate({ prompt: '搜索最新的 AI 新闻' })
console.log(result.text)
```

`webSearch()` 可配置：`{ thinking: 'enabled', maxTokens: 32768 }`——开启思考可在搜索前优化关键词，提高结果质量。

## 五、路径四：DeepSeek Harness / Agent 生态

- DeepSeek Harness 是面向 Agent 工具开发者的开发者预览，**内置 `web_search` 工具**。
- 支持 Claude Code、GitHub Copilot、OpenCode 等主流 Agent 工具直接接入 DeepSeek。
- 即使主对话模型切换到 opencode 等，内置联网搜索仍可用。
- 适用：想基于现有 Agent 框架（而非自研）获得 DeepSeek 联网能力的团队。

## 六、常见误区与选型建议

### 误区

1. **"网页版能联网，API 也能"** → 错。API 侧只有 `responses` 端点和 Anthropic 端点支持；`chat/completions` 传 `web_search` 会 400。
2. **"服务端搜索能拿到结果列表做引用展示"** → 错。黑盒注入，客户端只能拿到 `open_page` 的 URL 和 `queries`。
3. **"联网搜索很贵"** → 单次约 0.2~1 分，缓存命中后更便宜，远低于自接搜索 API + 额外拼 prompt 的 token 成本。

### 选型建议

| 需求 | 推荐 |
| --- | --- |
| 仅要联网回答，不需要引用展示 | 路径② Responses API，零集成 |
| 需要完整引用列表（标题+链接） | 路径③ Anthropic 端点（自带来源列表），或自接 Tavily/Serper |
| 已有 Agent 框架（Claude Code 等） | 路径④ Harness |
| 非开发者日常使用 | 路径① 网页版 |

## 七、本仓库（langchain 生态）落地实践

本仓库模型入口 `utils/std_model.py` 使用 `langchain_deepseek.ChatDeepSeek`，其 `api_base` 默认为 `https://api.deepseek.com/v1`（即 `chat/completions` 端点）。**该端点不支持原生 `web_search` 工具**（传了会被 400 拒绝），且 `ChatDeepSeek` 源码中也没有搜索相关参数。因此 langchain 生态内要联网，落地路径如下：

### 7.1 当前仓库做法（已就绪）：自接搜索工具

- `utils/std_tavily.py` 提供 `TavilyClient()`；
- `deepagents.ipynb` 通过 `langchain-tavily` 把搜索注册为 Agent 工具，模型自主决定何时调用，结果以 tool message 回填上下文。
- 优点：来源可控（标题+URL+摘要），可做引用展示；缺点：需要 Tavily API Key，搜索质量取决于所选搜索服务。

### 7.2 想要官方"自带"搜索：绕开 ChatDeepSeek，直连原生端点

langchain 的 `ChatDeepSeek` 未暴露搜索参数，需要直接用 OpenAI / Anthropic SDK 调原生端点：

- **Responses API**（黑盒注入，客户端拿不到结果列表，适合零集成场景）：

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.deepseek.com",
    api_key=os.environ["DEEPSEEK_API_KEY"],
)
resp = client.responses.create(
    model="deepseek-v4-flash",
    input="今天北京天气怎么样？",
    tools=[{"type": "web_search"}],
    stream=False,
)
print(resp.output_text)
```

- **Anthropic 兼容端点**（自带来源列表，可展示引用）：`POST https://api.deepseek.com/anthropic/v1/messages`，在 `tools` 中声明 `web_search_20250305` 即可。

### 7.3 选型建议

| 需求 | 推荐 |
| --- | --- |
| 沿用 langchain Agent 链路、来源可控可展示 | 继续用 Tavily 工具（仓库现状） |
| 零集成、不要求引用展示 | Responses API + `web_search` 工具 |
| 需要完整引用列表（Perplexity 式） | Anthropic 端点或 Tavily |

## 参考来源

- DeepSeek 官方 API 文档：[api-docs.deepseek.com](https://api-docs.deepseek.com)（含 OpenAI/Anthropic 兼容说明、V4 模型与定价）
- [CSDN《DeepSeek V4 正式版原生联网搜索实测——黑盒机制与低成本优势》](https://devpress.csdn.net/v1/article/detail/163394410)（2026-08-01，基于 Rescene 对 `api.deepseek.com/responses` 真实实测）
- [掘金《告别离线 Agent：deepseek-kit 内置 Web Search》](https://juejin.cn/post/7651603794846892047)（2026-06-16，Anthropic 兼容端点 + `web_search_20250305`）
- deepseek-kit 官方文档：[deepseek-kit.vercel.app](https://deepseek-kit.vercel.app)
