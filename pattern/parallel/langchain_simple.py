from utils.std_model import base_model

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tracers import ConsoleCallbackHandler
from langchain_core.runnables import RunnableParallel, Runnable, RunnablePassthrough

chatLLM = base_model()

summarize_chain: Runnable = (
        ChatPromptTemplate.from_messages([
            ("system", "简洁地总结以下主题："),
            ("user", "{topic}"),
        ])
        | chatLLM
        | StrOutputParser()
)

questions_chain: Runnable = (
        ChatPromptTemplate.from_messages([
            ("system", "生成关于以下主题的三个有趣问题："),
            ("user", "{topic}"),
        ])
        | chatLLM
        | StrOutputParser()
)

terms_chain: Runnable = (
        ChatPromptTemplate.from_messages([
            ("system", "从以下主题中识别 5-10 个关键术语，用逗号分隔："),
            ("user", "{topic}"),
        ])
        | chatLLM
        | StrOutputParser()
)

map_chain = RunnableParallel({
    "summary": summarize_chain,
    "questions": questions_chain,
    "terms": terms_chain,
    "topic": RunnablePassthrough(),
})

synthesis_prompt = ChatPromptTemplate.from_messages([
    ("system", """基于以下信息：
    摘要：{summary}
    相关问题：{questions}
    关键术语：{terms}
    综合一个全面的答案。
    """),
    ("user", "原始主题：{topic}"),
])

full_parallel_chain = map_chain | synthesis_prompt | chatLLM | StrOutputParser()


def run_parallel_example(topic: str) -> None:
    """
    异步调用具有特定主题的并行处理链
    并打印综合结果。
    参数：
        topic: 要由 LangChain 链处理的输入主题。
    """
    response = full_parallel_chain.invoke(input=topic, config={"callbacks": [ConsoleCallbackHandler()]})
    print(response)
    pass

if __name__ == "__main__":
    run_parallel_example("太空探索的历史")
