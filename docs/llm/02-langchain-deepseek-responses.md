# LangChain 调用 DeepSeek Responses API

> 结论时间：2026-08-20。基于仓库环境（`langchain-openai` 1.1.12）对 `https://api.deepseek.com/responses` 的真实调用实测。

## 目录

1. [结论速览](#一结论速览)
2. [为什么不用 langchain-deepseek 的 ChatDeepSeek](#二为什么不用-langchain-deepseek-的-chatedeepseek)
3. [最小可用示例](#三最小可用示例)
4. [联网搜索（web_search 工具）](#四联网搜索web_search-工具)
5. [输出格式：responses/v1 的 block 列表](#五输出格式responsesv1-的-block-列表)
6. [流式输出](#六流式输出)
7. [多轮对话（previous_response_id）](#七多轮对话previous_response_id)
8. [实测记录（2026-08-20）](#八实测记录2026-08-20)
9. [常见坑](#九常见坑)

## 一、结论速览

LangChain 调用 DeepSeek 的 Responses API（`https://api.deepseek.com/responses`，含原生联网搜索）的**正确姿势**：

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="deepseek-v4-flash",
    base_url="https://api.deepseek.com",   # SDK 自动拼出 /responses
    api_key="sk-...",
    use_responses_api=True,                 # 关键开关：走 /responses 而非 /chat/completions
)
model_with_search = model.bind_tools([{"type": "web_search"}])  # 联网搜索
```

要点：

| 项 | 值 |
| --- | --- |
| 包 | `langchain-openai`（≥ 0.3.26 才有 `use_responses_api`） |
| 不要用 | `langchain-deepseek` 的 `ChatDeepSeek`（封装的是 chat/completions） |
| 端点路由 | `base_url` 后由 openai SDK 自动拼 `/responses` |
| 联网搜索 | `bind_tools([{"type": "web_search"}])`，`tool_choice` 默认 `auto` |
| 输出格式 | responses/v1 的 block 列表（`reasoning` / `text` / `web_search_call`） |

## 二、为什么不用 langchain-deepseek 的 ChatDeepSeek

- `langchain-deepseek` 提供的 `ChatDeepSeek` 继承 `BaseChatOpenAI`，走的是 **chat/completions** 风格。
- 上篇文档已实测：`chat/completions` 端点传 `web_search` 工具会被 400 拒绝。
- 因此**要联网搜索必须走 responses 端点**，只能使用 `langchain-openai` 的 `ChatOpenAI` + `use_responses_api=True`（新版已内置 Responses API 支持，无需独立 `OpenAIResponses` 类）。

## 三、最小可用示例

```python
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="deepseek-v4-flash",
    base_url="https://api.deepseek.com",
    api_key="sk-...",
    use_responses_api=True,
)
resp = model.invoke([HumanMessage("用一句话介绍 DeepSeek")])
print(resp.content)
```

## 四、联网搜索（web_search 工具）

```python
model = ChatOpenAI(model="deepseek-v4-flash", base_url="https://api.deepseek.com",
                   api_key="sk-...", use_responses_api=True)
model_with_search = model.bind_tools([{"type": "web_search"}])
resp = model_with_search.invoke([HumanMessage("搜索一下 DeepSeek 最近发布了什么新模型")])
```

- 服务端黑盒注入：搜索结果直接进上下文，客户端拿不到结果列表，只能从 `web_search_call` 块拿到搜索词（`search` 动作）和打开过的页面 URL（`open_page` 动作）。
- 无需自建搜索引擎 / Tavily / Serper，成本见 [01-deepseek-websearch.md](./01-deepseek-websearch.md)。

## 五、输出格式：responses/v1 的 block 列表

`use_responses_api=True` 时 `resp.content` 不再是字符串，而是 **block 列表**，常见块类型：

| block type | 含义 | 关键字段 |
| --- | --- | --- |
| `reasoning` | 思考链 | `content` |
| `text` | 最终回答 | `text` |
| `web_search_call` | 联网搜索动作 | `action.type`（`search`/`open_page`）、`action.queries`、`action.url` |

解析示例：

```python
for block in resp.content:
    if not isinstance(block, dict):
        continue
    t = block.get("type")
    if t == "text":
        print(block.get("text"))
    elif t == "reasoning":
        print(block.get("content"))
    elif t == "web_search_call":
        action = block.get("action", {})
        if action.get("type") == "search":
            print("queries:", action.get("queries"))   # 注意 queries 带 ws_call_id= 尾巴，需清洗
        elif action.get("type") == "open_page":
            print("url:", action.get("url"))
```

## 六、流式输出

```python
for chunk in model.stream([HumanMessage("今天北京天气怎么样？")]):
    print(str(chunk.content), end="")
```

## 七、多轮对话（previous_response_id）

Responses API 原生支持用 `previous_response_id` 衔接上下文（比把历史全塞进 messages 省 token）：

```python
resp1 = model.invoke([HumanMessage("介绍一下 RAG")])
resp2 = model.invoke(
    [HumanMessage("那它和微调有什么区别？")],
    previous_response_id=resp1.additional_kwargs.get("response_id"),
)
```

## 八、实测记录（2026-08-20）

环境：仓库 `.venv`，`langchain-openai` 1.1.12，模型 `deepseek-v4-flash`，`base_url="https://api.deepseek.com"`。

1. **基础调用**：成功，返回 block 列表（reasoning + text）。
2. **联网搜索**：`bind_tools([{"type": "web_search"}])` 成功触发搜索，响应中出现 `web_search_call` 块：
   - `search` 动作：queries 含 `ws_call_id=call_xxx` 尾巴（与 01 文档结论一致）；
   - `open_page` 动作：返回具体 URL（无 title）。
3. **usage 样例**：input 30145 tokens（cache_read 20608）、output 1876（reasoning 989）。按 [01 文档](./01-deepseek-websearch.md) 单价估算单次约 1~2 分钱。
4. 完整可运行示例已写入仓库：`langchain/deepseek_responses_example.py`（含基础调用 / 联网搜索 / 流式 / 多轮四种用法）。

## 九、常见坑

1. **用了 `ChatDeepSeek` 想联网** → 换 `ChatOpenAI` + `use_responses_api=True`。
2. **`use_responses_api` 参数不存在** → `langchain-openai` 版本过低，需 ≥ 0.3.26（当前仓库 1.1.12）。
3. **`base_url` 写成了 `.../responses`** → SDK 会自动拼接，写根地址 `https://api.deepseek.com` 即可。
4. **`resp.content` 是字符串却发现是列表** → responses 端点的正常格式，按 block 类型解析。
5. **展示引用来源** → 从 `open_page` 的 URL 抓标题组装；纯 `search` 动作只有搜索词没有 URL。

## 参考

- 上篇：[01-deepseek-websearch.md](./01-deepseek-websearch.md)（Responses API 黑盒机制、成本、流式事件时序）
- 官方：https://api-docs.deepseek.com
- 源码：`langchain_openai/chat_models/base.py`（`use_responses_api`、内置工具 `web_search`）
