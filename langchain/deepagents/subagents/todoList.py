import json
import sys

from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware

from utils.std_model import base_model

agent = create_deep_agent(
    model=base_model(),
    middleware=[TodoListMiddleware()],
)

resp = agent.stream_events(
    {
        "messages": [
            {
                "role": "user",
                "content": "请制定一个完成以下调研的分步计划（至少4个步骤），然后按计划执行：调研AI agent产品的工程发展趋向。请务必先调用 write_todos 工具制定计划再开始。",
            }
        ]
    },
    version="v3",
)


def show_todos_preview(args: str) -> None:
    """write_todos 参数增量到达时，单行实时刷新计划预览。"""
    try:
        todos = json.loads(args).get("todos", [])
    except Exception:
        return
    parts = [f"{t.get('status', '?')}:{t.get('content', '')[:16]}" for t in todos]
    sys.stdout.write(f"\r[计划更新中] {' | '.join(parts)}")
    sys.stdout.flush()


for message in resp.messages:
    # 按原始事件流迭代：文本增量 / 工具调用增量按到达顺序交错出现
    for event in message:
        if event["event"] != "content-block-delta":
            continue
        delta = event["delta"]
        t = delta["type"]
        if t == "text-delta":
            # 1) 文本 token 实时打印
            print(delta.get("text", ""), end="", flush=True)
        elif t == "block-delta":
            # 2) 工具调用参数增量（deepseek 以 block-delta 形式发送）
            fields = delta.get("fields", {})
            if fields.get("type") == "tool_call_chunk" and fields.get("name") == "write_todos":
                show_todos_preview(fields.get("args", ""))

    # 3) 消息结束：换行并输出该消息最终的完整计划
    sys.stdout.write("\n")
    for tc in message.tool_calls.get():
        if tc["name"] == "write_todos":
            print(f"[write_todos 完成] {tc['args']['todos']}", flush=True)
