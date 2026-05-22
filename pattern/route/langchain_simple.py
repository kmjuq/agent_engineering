from utils.std_model import base_model
from langchain_core.runnables import RunnablePassthrough, RunnableBranch
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

chatLLM = base_model()


## --- 定义模拟子智能体处理程序（相当于 ADK 的 sub_agents）---
def booking_handler(request: str) -> str:
    """模拟预订智能体请求。"""
    print("\n--- 委托给预订处理程序 ---")
    return f"预订处理程序处理了请求：'{request}'。结果：模拟预订操作。"


def info_handler(request: str) -> str:
    """模拟信息智能体请求。"""
    print("\n--- 委托给信息处理程序 ---")
    return f"信息处理程序处理了请求：'{request}'。结果：模拟信息检索。"


def unclear_handler(request: str) -> str:
    """处理无法委托的请求。"""
    print("\n--- 处理不清楚的请求 ---")
    return f"协调器无法委托请求：'{request}'。请澄清。"


coordinator_router_prompt = ChatPromptTemplate.from_messages([
    ("system", """分析用户的请求并确定哪个专家处理程序应处理它。
     - 如果请求与预订航班或酒店相关，
        输出 'booker'。
     - 对于所有其他一般信息问题，输出 'info'。
     - 如果请求不清楚或不适合任一类别，
        输出 'unclear'。
     只输出一个词：'booker'、'info' 或 'unclear'。"""),
    ("user", "{request}")
])

coordinator_router_chain = coordinator_router_prompt | chatLLM | StrOutputParser()

branches = {
    "booker": RunnablePassthrough.assign(output=lambda x: booking_handler(x['request']['request'])),
    "info": RunnablePassthrough.assign(output=lambda x: info_handler(x['request']['request'])),
    "unclear": RunnablePassthrough.assign(output=lambda x: unclear_handler(x['request']['request'])),
}

delegation_branch = RunnableBranch(
    (lambda x: x['decision'].strip() == 'booker', branches["booker"]),  # 添加了 .strip()
    (lambda x: x['decision'].strip() == 'info', branches["info"]),  # 添加了 .strip()
    branches["unclear"]  # 'unclear' 或任何其他输出的默认分支
)

chain = {
                        "decision": coordinator_router_chain,
                        "request": RunnablePassthrough()
                    } | delegation_branch | (lambda x: x['output'])

print("--- 运行预订请求 ---")
request_a = "给我预订去伦敦的航班。"
result_a = chain.invoke({"request": request_a})
print(f"最终结果 A: {result_a}")

print("\n--- 运行信息请求 ---")
request_b = "意大利的首都是什么？"
result_b = chain.invoke({"request": request_b})
print(f"最终结果 B: {result_b}")

print("\n--- 运行不清楚的请求 ---")
request_c = "告诉我关于量子物理学的事。"
result_c = chain.invoke({"request": request_c})
print(f"最终结果 C: {result_c}")
