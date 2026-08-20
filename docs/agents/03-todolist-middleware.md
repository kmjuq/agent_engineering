# TodoListMiddleware 的计划处理机制（langchain）

> 更新记录：
> - 2026-08-20 初稿（源码定位：`.venv/lib/python3.14/site-packages/langchain/agents/middleware/todo.py`）
> - 2026-08-20 补充：运行方式（`PYTHONPATH=.`）、实测结果（write_todos 触发条件、ToolMessage 观察、工具名过滤）
> - 2026-08-20 补充：**"边输出 token 边处理 todo"的实现**——按原始事件流迭代（`for event in message`），见 §五
>
> 实验入口：`langchain/deepagents/subagents/todoList.py`

## 一、问题

使用 `create_deep_agent(..., middleware=[TodoListMiddleware()])` 后，agent 有了 `write_todos` 工具（TodoList 计划能力），但 `todoList.py` 里原来只打印 `message.text`（模型文本 token），**看不到计划（todo list）的制定/更新过程**。

## 二、机制：langchain 如何"看到"计划

`TodoListMiddleware` 依赖 langgraph 的 **状态（state）** 与 **middleware 钩子**，全流程如下：

### 1. 工具注入（构造函数）

```python
self.tools = [
    StructuredTool.from_function(
        name="write_todos",
        func=_write_todos, coroutine=_awrite_todos,
        args_schema=WriteTodosInput, infer_schema=False,
    )
]
```

`create_deep_agent` / `create_agent` 会把所有 middleware 的 `tools` 合入 agent 的工具集，模型即可调用 `write_todos(todos=[...])`。

### 2. System prompt 注入（`wrap_model_call` / `awrap_model_call`）

每次模型调用前，把 `WRITE_TODOS_SYSTEM_PROMPT`（何时用、状态机、完成规则等使用指南）**追加到 system message 末尾**：

```python
new_system_content = [
    *request.system_message.content_blocks,
    {"type": "text", "text": f"\n\n{self.system_prompt}"},
]
return handler(request.override(system_message=new_system_message))
```

这是模型"知道"要主动规划的依据。

### 3. 模型制定/更新计划

模型在回答中产生 `write_todos` 工具调用（tool_call），参数为完整的新 todo 列表（含每个 item 的 `content` 与 `status: pending/in_progress/completed`）。

### 4. 状态更新（`_write_todos` 工具实现）

工具执行后返回 `Command`，由 langgraph 应用到图的 state：

```python
return Command(update={
    "todos": todos,   # state.todos 整表替换为最新计划
    "messages": [ToolMessage(f"Updated todo list to {todos}", tool_call_id=...)],  # 追加反馈消息
})
```

即：**计划保存在 graph state 的 `todos` 字段**（每次整表覆盖），同时每次更新都会产生一条 `ToolMessage("Updated todo list to [...]")` 进入消息历史。

### 5. 防冲突（`after_model` / `aafter_model`）

`write_todos` 每次调用都会整表替换，禁止同一轮**并行**多次调用：若检测到同一轮有 >1 个 `write_todos` tool_call，返回 `status="error"` 的 ToolMessage，让模型重试。

### 6. State schema（`PlanningState`）

```python
class PlanningState(AgentState[ResponseT]):
    todos: Annotated[NotRequired[list[Todo]], OmitFromInput]
```

`todos` 是 state 的**可选输入**字段（`OmitFromInput`：用户/上游不必提供，由工具写入），并在 `agent.invoke(...)` 的结果中可见。

## 三、如何观察计划处理过程（代码层面）

`stream_events(version="v3")` 返回 `GraphRunStream`，其 `messages` 是 `StreamChannel[ChatModelStream]`——**每条消息（AI / Tool）一个流对象**。`ChatModelStream` 提供：

| 投影 | 说明 |
| --- | --- |
| `.text` | 模型文本 token 增量流（`str()` 取全文） |
| `.reasoning` | 推理内容 |
| `.tool_calls` | `ToolCallChunk` 增量；`.get()` 返回完整 `list[ToolCall]` |
| `.output` | 阻塞等待流完成后返回组装好的消息对象 |

因此"计划处理过程"由两个可观测载体构成：

1. **AI 消息的 `tool_calls`**：模型每次调用 `write_todos` 传入的最新计划（`tc['args']['todos']`）；
2. **ToolMessage**：工具执行后的反馈 `"Updated todo list to [...]"`。

修改后的 `todoList.py`（关键片段）：

```python
for message in resp.messages:
    # 1) 模型生成的文本 token
    for token in message.text:
        print(token, end="", flush=True)

    # 2) 模型调用 write_todos 工具 -> 计划的制定/更新过程
    for tc in message.tool_calls.get():
        print(f"\n[write_todos] 计划更新: {tc['args']['todos']}", flush=True)

    # 3) 工具执行后的反馈 ToolMessage
    output = message.output
    if getattr(output, "type", "") == "tool":
        print(f"\n[TodoList反馈] {output.content}", flush=True)
```

> 说明：`message.output` 的类型标注为 `AIMessage`（v3 协议下运行时对 ToolMessage 流返回对应消息对象），故用 `getattr(output, "type", "")` 做运行时类型判断，避免类型检查器误报。

## 四、运行方式与实测结果

### 1. 运行命令（必须在项目根目录）

```bash
cd /Users/kmj/WorkSpace/git/agent_engineering
PYTHONPATH=. uv run python langchain/deepagents/subagents/todoList.py
```

两个必要前提：

- **`PYTHONPATH=.` 必须加**：本项目 `pyproject.toml` 无 `build-system`，uv 不把项目本身安装为包，项目根不在 `sys.path`；不加会报 `ModuleNotFoundError: No module named 'utils'`。
- **工作目录必须是项目根**：脚本里 `from utils.std_model import base_model` 是相对项目根的导入。
- `.env` 需在根目录且含 `DEEPSEEK_API_KEY`（`utils/env.py` 自动加载）。

### 2. 实测结果（deepseek-v4-flash）

| 观察项 | 结果 |
| --- | --- |
| write_todos 是否被调用 | **不一定**。默认提示词"请调研…"时模型可能直接输出不规划；**明确要求"务必先调用 write_todos 制定计划"时必然调用**（系统提示词本就要求复杂任务先规划，但 flash 模型遵循度有波动） |
| 计划更新轨迹 | 可见完整生命周期：初始计划（step1 `in_progress`）→ 逐步 `completed` + 下一项 `in_progress` → 全部 `completed`，每次 `write_todos` 都是**整表替换** |
| ToolMessage（`[TodoList反馈]`） | v3 流中工具执行结果被聚合在 AI 消息中，`messages` 流里未出现独立的 `type="tool"` 消息；**计划状态以 tool_calls 为准**，该分支在实际运行中不会触发（保留作为兜底） |
| 其他工具调用 | 流中还会出现 `ls`/`glob`/`write_file`/`execute` 等 deepagents 内置工具，**必须按 `tc["name"] == "write_todos"` 过滤**，否则 `tc['args']['todos']` 会 KeyError |

### 3. 关键代码修正记录

1. **按工具名过滤**：`message.tool_calls.get()` 返回该轮全部工具调用（含 `ls`、`write_file` 等），直接取 `tc['args']['todos']` 会 `KeyError: 'todos'`，需先判断 `tc["name"] == "write_todos"`。
2. **提示词**：为保证可复现地看到规划过程，示例提示词改为"请制定一个完成以下调研的分步计划（至少4个步骤）…请务必先调用 write_todos 工具制定计划再开始"。

## 五、如何实现"边输出 token 边处理 todo"

### 1. 底层数据本来就是交错的

实测（v3 流 + deepseek-v4-flash）确认：单条消息的**原始事件流是文本增量与工具调用增量按到达顺序交错**的：

```
[文本] 我将按照您的要求，先制定调研计划，再逐步执行。让我先创建计划。
[工具增量] name='write_todos' args='{"todos'
[工具增量] name='write_todos' args='{"todos": [{"content": "盘点本地工作目录中已有的资料/文档...'
[工具增量] name='write_todos' args='{"todos": [{"content": "盘点本地工作目录中已有的资料/文档，确认调研起点与可复用素材", "status": "in_progress"}, ...'
```

### 2. 为什么之前的写法"没办法边输出边处理"

`ChatModelStream` 的 `.text` / `.tool_calls` 是**两个独立投影（projection）**，各自缓冲：

```python
# 错误写法：串行消费两个投影
for token in message.text:          # ① 阻塞直到整条消息文本流结束
    print(token, end="", flush=True)
for tc in message.tool_calls.get(): # ② 文本结束后才一次性拿完整工具调用
    ...
```

`for token in message.text` 会**一直阻塞到该消息的文本流全部结束**，随后 `.tool_calls.get()` 才返回组装好的完整列表。视觉上就是"文本先全部打完、todo 突然蹦出"。

### 3. 正确写法：按原始事件流迭代

```python
import json, sys

def show_todos_preview(args: str) -> None:
    try:
        todos = json.loads(args).get("todos", [])
    except Exception:
        return
    parts = [f"{t.get('status', '?')}:{t.get('content', '')[:16]}" for t in todos]
    sys.stdout.write(f"\r[计划更新中] {' | '.join(parts)}")
    sys.stdout.flush()

for message in resp.messages:
    for event in message:            # 按原始到达顺序：文本/工具增量交错
        if event["event"] != "content-block-delta":
            continue
        delta = event["delta"]
        t = delta["type"]
        if t == "text-delta":
            print(delta.get("text", ""), end="", flush=True)  # 文本 token 实时打印
        elif t == "block-delta":                              # deepseek 走这个
            fields = delta.get("fields", {})
            if fields.get("type") == "tool_call_chunk" and fields.get("name") == "write_todos":
                show_todos_preview(fields.get("args", ""))    # 单行实时刷新计划
    sys.stdout.write("\n")
    for tc in message.tool_calls.get():   # 消息结束输出最终完整计划
        if tc["name"] == "write_todos":
            print(f"[write_todos 完成] {tc['args']['todos']}", flush=True)
```

实测输出（交错效果）：

```
我将按照您的要求，先使用 write_todos 制定分步调研计划，然后按计划执行。[计划更新中] in_progress:探索本地文件系统... | pending:阅读并检索资料... | ...
[write_todos 完成] [{'content': '探索本地文件系统...', 'status': 'in_progress'}, ...]
计划已制定。现在开始执行第1步：探索文件系统，确认可用的调研资料。
```

### 4. 细节说明

- **`block-delta` vs `tool_call_chunk`**：deepseek 的工具调用增量以 `block-delta`（`fields.type == "tool_call_chunk"`）发送，`args` 是**累积的 JSON 快照**；其他提供方可能直接发 `tool_call_chunk`。两种都处理可兼容。
- **预览解析容错**：增量过程中 JSON 不完整，`json.loads` 会抛异常，需 `try/except` 忽略。
- **Claude Code / Cursor 类产品**的"边输出边更新"正是消费原始事件流（或 UI 并行渲染），而非串行消费投影。

## 六、相关链接

- [01-plan-mode-deepagents.md](./01-plan-mode-deepagents.md)：deepagents Plan 模式（另一种计划实现，Planner + subagent）
- [02-codebuddy-agent-loop-deepagents.md](./02-codebuddy-agent-loop-deepagents.md)：Agent Loop 双层架构
- 上游源码：`.venv/lib/python3.14/site-packages/langchain/agents/middleware/todo.py`；`langgraph/stream/run_stream.py`（GraphRunStream）；`langchain_core/language_models/chat_model_stream.py`（ChatModelStream）
