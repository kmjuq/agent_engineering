from tavily import TavilyClient

from utils.env import auto_load_env


@auto_load_env
def tavily_client():
    return TavilyClient()