import os

from langchain_openai import ChatOpenAI

from utils.env import auto_load_env


def model_template(model_name):
    return ChatOpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model=model_name,
    )


@auto_load_env
def base_model():
    return model_template(os.getenv("ALIYUN_TEXT_MODEL"))


@auto_load_env
def basic_model():
    return model_template("qwen-plus")


@auto_load_env
def advanced_model():
    return model_template("qwen-turbo")
