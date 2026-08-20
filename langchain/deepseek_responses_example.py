"""LangChain 调用 DeepSeek Responses API（含原生联网搜索）示例。

环境要求：
- langchain-openai >= 0.3.26（use_responses_api 参数）
- openai SDK（langchain-openai 的依赖）
- .env 中配置 DEEPSEEK_API_KEY

关键点：
- 不要用 langchain-deepseek 的 ChatDeepSeek（它封装的是 chat/completions，不支持 web_search）
- 用 langchain_openai.ChatOpenAI + use_responses_api=True，走 https://api.deepseek.com/responses
- 联网搜索：bind_tools([{"type": "web_search"}])，模型自主决定是否搜索（tool_choice 默认 auto）

实测：2026-08-20，langchain-openai 1.1.12，模型 deepseek-v4-flash。
"""

import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

load_dotenv()

BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-flash"


def build_model(with_web_search: bool = True) -> ChatOpenAI:
    model = ChatOpenAI(
        model=MODEL,
        base_url=BASE_URL,
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        use_responses_api=True,  # 关键：走 /responses 端点而不是 /chat/completions
    )
    if with_web_search:
        # 声明服务端内置工具，模型自主决定是否搜索
        return model.bind_tools([{"type": "web_search"}])
    return model


def basic_call() -> None:
    """基础调用：无联网搜索。"""
    model = build_model(with_web_search=False)
    resp = model.invoke([HumanMessage("用一句话介绍 DeepSeek")])
    print("basic_call:", resp.content)


def web_search_call() -> None:
    """联网搜索调用：响应 content 为 responses/v1 格式的 block 列表。"""
    model = build_model(with_web_search=True)
    resp = model.invoke([HumanMessage("搜索一下 DeepSeek 最近发布了什么新模型")])

    for block in resp.content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            print("[text]", block.get("text"))
        elif btype == "reasoning":
            print("[reasoning]", block.get("content"))
        elif btype == "web_search_call":
            action = block.get("action", {})
            if action.get("type") == "search":
                print("[search queries]", action.get("queries"))
            elif action.get("type") == "open_page":
                print("[open_page]", action.get("url"))
    print("usage:", resp.usage_metadata)


def web_search_stream() -> None:
    """联网搜索 + 流式输出。"""
    model = build_model(with_web_search=True)
    for chunk in model.stream([HumanMessage("今天北京天气怎么样？")]):
        print(str(chunk.content), end="")


def multi_turn() -> None:
    """多轮对话：用 previous_response_id 衔接上下文（Responses API 特性）。"""
    model = build_model(with_web_search=False)
    resp1 = model.invoke([HumanMessage("介绍一下 RAG 是什么")], previous_response_id=None)
    resp2 = model.invoke(
        [HumanMessage("那它和微调有什么区别？")],
        previous_response_id=resp1.additional_kwargs.get("response_id"),
    )
    print("multi_turn:", resp2.content)


if __name__ == "__main__":
    print("=== basic_call ===")
    basic_call()
    print("\n=== web_search_call ===")
    web_search_call()
