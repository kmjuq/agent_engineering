import os
import re
from typing import TypedDict, Callable, Any, List, Dict, Optional

from openai import OpenAI
from tavily import TavilyClient

from utils.env import load_env

load_env()

client = TavilyClient()

SYSTEM_PROMPT = """
你是一个能够通过思考与调用工具来回答用户问题的 AI 助手。

可用工具列表，调用时请严格按照以下名称书写，区分大小写：
{tools}

你必须严格按照 “Thought → Action → Observation” 的循环来解决问题：
- 每次回答只能包含 Thought 和 Action 两个部分。
- Observation 将由系统根据你调用的工具结果自动返回给你，你绝不可以自行编造 Observation。
- 收到 Observation 后，再进行下一轮 Thought 和 Action，直到能够给出最终答案。
- 若工具结果无效或不足，你可以再次思考并选择其他工具。

Action 格式（只能选择其一）：
- 调用工具：工具名[参数]
- 结束回答：Finish[最终答案]  （注意：最终答案必须为单行文本，请使用编号或逗号分隔多项内容，不要使用换行符）

可参考示例：
用户: 华为最新的手机型号有哪些？
AI:
Thought: 现有 search 工具提供，需要实时信息，可以调用 search 工具获取信息。
Action: search[华为最新手机型号 2025]

（系统返回 Observation: 搜索到华为 Mate 70 和 Pura 80 Pro+ 的相关报道）

AI:
Thought: 已获得两款型号，可以总结卖点进行回答。
Action: Finish[华为最新的手机包括 Mate 70 和 Pura 80 Pro+……]

行为要求：
- 对于实效性问题，必须先通过 search 工具查询当前时间，然后使用工具返回的时间作为当前时间
- Finish 中的最终答案必须为单行，不得包含换行符（\n），如需罗列多项请用逗号或分号分隔

现在请解决以下问题：
Question: {question}
History: {history}
"""


def search(query: str) -> str:
    api_result = client.search(query=query, country="china",include_answer=True,include_raw_content=True)
    return api_result['answer']


class Tool(TypedDict):
    name: str
    description: str
    func: Callable[..., Any]


tools = {}


def register_tool(name: str, description: str, func: Callable[..., Any]):
    tool = Tool(name=name, description=description, func=func)
    tools[tool["name"]] = tool


def list_tools():
    return "".join(f"{tool['name']}: {tool['description']}\n" for tool in tools.values())


class OpenAICompatibleClient:
    """
    一个用于调用任何兼容OpenAI接口的LLM服务的客户端。
    """

    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, messages: List[Dict[str, str]]) -> str:
        """调用LLM API来生成回应。"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
                temperature=0.1,
            )
            answer = response.choices[0].message.content
            return answer
        except Exception as e:
            print(f"调用LLM API时发生错误: {e}")
            return "错误:调用语言模型服务时出错。"


llm = OpenAICompatibleClient(
    model="deepseek-v4-flash",
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)


def parse_output(text: str) -> tuple[Optional[str], Optional[str]]:
    """解析LLM的输出，提取Thought和Action。
    """
    # Thought: 匹配到 Action: 或文本末尾
    thought_match = re.search(r"Thought:\s*(.*?)(?=\nAction:|$)", text, re.DOTALL)
    # Action: 匹配到文本末尾
    action_match = re.search(r"Action:\s*(.*?)$", text, re.DOTALL)
    thought = thought_match.group(1).strip() if thought_match else None
    action = action_match.group(1).strip() if action_match else None
    return thought, action


def parse_action(action_text: str):
    """解析Action字符串，提取工具名称和输入。
    """
    match = re.match(r"(\w+)\[(.*)\]", action_text, re.DOTALL)
    if match:
        return match.group(1), match.group(2)
    return None, None

def llm_call():
    register_tool(
        'search',
        '一个网页搜索引擎。当你需要回答关于时事、事实以及在你的知识库中找不到的信息时，应使用此工具。',
        search
    )
    tool_prompt = list_tools()
    question = "华为最新的手机型号有哪些？"
    prompt = SYSTEM_PROMPT.format(tools=tool_prompt, question=question, history="")
    final_answer = False

    history = []
    step = 0
    while not final_answer:
        print(f"第 {step} 轮")
        prompt = SYSTEM_PROMPT.format(tools=tool_prompt, question=question, history="\n".join(history))
        messages = [{"role": "user", "content": prompt}]

        print(f"{"\n".join(history)}")

        response_txt = llm.generate(messages=messages)

        print(f"{response_txt}")

        # 匹配Thought Action
        thought, action = parse_output(response_txt)

        if thought:
            history.append(f"Thought: {thought}")

        if action:
            history.append(f"Action: {action}")

        if not action:
            history.append("警告:未能解析出有效的Action，重试。")

        if action.startswith("Finish"):
            # 如果是Finish指令，提取最终答案并结束
            final_answer = re.match(r"Finish\[(.*)\]", action).group(1)
            print(f"最终答案: {final_answer}")
            break

        tool_name, tool_input = parse_action(action)
        if not tool_name or not tool_input:
            history.append("未遵循Action格式")

        if tool_name not in tools:
            observation = f"错误：未找到名为 '{tool_name}' 的工具。当前可用工具：{list(tools.keys())}。请使用准确名称重试。"
        else:
            observation = tools[tool_name]['func'](tool_input)  # 调用真实工具

        history.append(f'observation: {observation}')
        step += 1


if __name__ == "__main__":
    # search("华为 Pura 90 系列 2026 型号")
    llm_call()