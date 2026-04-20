import os
from functools import wraps

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


# ======================
# 自动加载 .env 的装饰器
# ======================
def auto_load_env(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        load_dotenv()  # 每次调用函数前都会执行！
        return func(*args, **kwargs)

    return wrapper


@auto_load_env
def base_model():
    chatLLM = ChatOpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model=os.getenv("ALIYUN_TEXT_MODEL"),
    )
    return chatLLM


@auto_load_env
def basic_model():
    return ChatOpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
    )


@auto_load_env
def advanced_model():
    return ChatOpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-turbo",
    )
