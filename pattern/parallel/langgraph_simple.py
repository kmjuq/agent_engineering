from typing import TypedDict

from langgraph.constants import START, END
from langgraph.graph import StateGraph

from utils.std_model import base_model

llm = base_model()


class JokeState(TypedDict):
    topic: str
    joke: str
    story: str
    poem: str
    combined_output: str


def call_llm1(state: JokeState):
    """ LLM call to generate initial joke """
    msg = llm.invoke(f"Write a joke about {state['topic']}")
    return {
        "joke": msg.content,
    }


def call_llm2(state: JokeState):
    """ LLM call to generate story """
    msg = llm.invoke(f"Write a story about {state['topic']}")
    return {
        "story": msg.content
    }


def call_llm3(state: JokeState):
    """ LLM call to generate poem """
    msg = llm.invoke(f"Write a poem about {state['topic']}")
    return {
        "poem": msg.content
    }


def aggregator(state: JokeState):
    """ Combine the joke, story and poem into a single output """
    combined = f"Here's a story, joke, and poem about {state['topic']}!\n\n"
    combined += f"STORY:\n{state['story']}\n\n"
    combined += f"JOKE:\n{state['joke']}\n\n"
    combined += f"POEM:\n{state['poem']}"
    return {
        "combined_output": combined
    }

if __name__ == "__main__":
    graph_builder = StateGraph(JokeState)

    # node
    graph_builder.add_node(call_llm1.__name__, call_llm1)
    graph_builder.add_node(call_llm2.__name__, call_llm2)
    graph_builder.add_node(call_llm3.__name__, call_llm3)
    graph_builder.add_node(aggregator.__name__, aggregator)

    # edge
    graph_builder.add_edge(START, call_llm1.__name__)
    graph_builder.add_edge(START, call_llm2.__name__)
    graph_builder.add_edge(START, call_llm3.__name__)
    graph_builder.add_edge(call_llm1.__name__, aggregator.__name__)
    graph_builder.add_edge(call_llm2.__name__, aggregator.__name__)
    graph_builder.add_edge(call_llm3.__name__, aggregator.__name__)
    graph_builder.add_edge(aggregator.__name__, END)

    graph = graph_builder.compile()

    resp = graph.invoke({
        "topic": "cat"
    })
    print(resp)


