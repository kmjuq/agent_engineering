from langchain_deepseek import ChatDeepSeek

from utils.env import auto_load_env


def model_template(model_name):
    return ChatDeepSeek(
        model=model_name,
    )


@auto_load_env
def base_model():
    return model_template("deepseek-v4-flash")


@auto_load_env
def basic_model():
    return model_template("deepseek-v4-flash")


@auto_load_env
def advanced_model():
    return model_template("deepseek-v4-pro")
