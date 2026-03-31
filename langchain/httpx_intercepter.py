import logging

import httpx

# 配置日志（确保能打印）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# 1. 定义同步客户端（带日志钩子，不破坏流）
def get_base_client():
    def log_request(request: httpx.Request):
        logging.info(f">>> 拦截请求: {request.method} {request.url}")
        logging.info(f">>> 请求头: {dict(request.headers)}")
        # 仅读取请求体（请求体读取不影响后续，因为是可复用的）
        if request.content:
            logging.info(f">>> 请求体: {request.content.decode(errors='ignore')}")

    def log_response(response: httpx.Response):
        logging.info(f"<<< 响应状态: {response.status_code}")
        logging.info(f"<<< 响应头: {dict(response.headers)}")

    # 用 event_hooks 注入日志逻辑，不修改 transport
    return httpx.Client(
        event_hooks={
            "request": [log_request],
            "response": [log_response]
        }
    )

# 2. 定义异步客户端（同理）
def get_async_client():
    async def log_request(request: httpx.Request):
        logging.info(f">>> 拦截请求: {request.method} {request.url}")
        logging.info(f">>> 请求头: {dict(request.headers)}")
        if request.content:
            logging.info(f">>> 请求体: {request.content.decode(errors='ignore')}")

    async def log_response(response: httpx.Response):
        logging.info(f"<<< 响应状态: {response.status_code}")
        logging.info(f"<<< 响应头: {dict(response.headers)}")

    return httpx.AsyncClient(
        event_hooks={
            "request": [log_request],
            "response": [log_response]
        }
    )
