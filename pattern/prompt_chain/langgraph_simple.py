from typing import TypedDict

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from utils.std_model import base_model

llm = base_model()


class JokeState(TypedDict):
    topic: str
    joke: str
    improved_joke: str


class HasPunchline(TypedDict):
    has_punchline: bool


def generate_joke(state: JokeState):
    """ 根据话题生成笑话 """
    topic = state["topic"]

    msg = llm.invoke(f"根据主题“{topic}”生成一个笑话")
    return {
        "joke": msg.content,
    }


def improve_joke(state: JokeState):
    """ 提升笑话的好笑程度 """

    msg = llm.invoke(f"通过加入文字游戏让这个笑话更好笑: {state['joke']}")
    return {"improved_joke": msg.content}


def check_joke(state: JokeState):
    joke = state['joke']

    llm_with_tools = llm.with_structured_output(HasPunchline)

    resp = llm_with_tools.invoke(f"判断笑话:[{joke}]是否有包袱？")

    if resp["has_punchline"]:
        return END
    else:
        return improve_joke.__name__


if __name__ == "__main__":
    graph_builder = StateGraph(JokeState)

    graph_builder.add_node(generate_joke.__name__, generate_joke)
    graph_builder.add_node(improve_joke.__name__, improve_joke)

    graph_builder.add_edge(START, generate_joke.__name__)
    graph_builder.add_conditional_edges(generate_joke.__name__, check_joke, [END, improve_joke.__name__])
    graph_builder.add_edge(improve_joke.__name__, END)

    graph = graph_builder.compile()

    init_state = {
        "topic": "猫",
    }
    resp = graph.invoke(init_state)
    print(resp)

