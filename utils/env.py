# ======================
# 自动加载 .env 的装饰器
# ======================
import os
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（基于 env.py 自身位置）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"


def auto_load_env(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        load_dotenv(dotenv_path=_ENV_PATH)  # 使用显式路径，避免 os.getcwd() 失败
        return func(*args, **kwargs)

    return wrapper