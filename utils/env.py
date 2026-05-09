# ======================
# 自动加载 .env 的装饰器
# ======================
from functools import wraps

from dotenv import load_dotenv


def auto_load_env(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        load_dotenv()  # 每次调用函数前都会执行！
        return func(*args, **kwargs)

    return wrapper