from typing import Literal, TypedDict

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.constants import START
from langgraph.errors import GraphInterrupt
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field

from utils.std_model import base_model

llm = base_model()


class Route(BaseModel):
    step: Literal["poem", "story", "joke"] = Field(
        None, description="The next step in the routing process"
    )


class State(TypedDict):
    input: str
    output: str
    decision: str


def llm_call_joke(state: State):
    """ create a joke """
    result = llm.invoke(state["input"])
    return {"output": result.content}


def llm_call_poem(state: State):
    """ create a poem """
    result = llm.invoke(state["input"])
    return {"output": result.content}


def llm_call_story(state: State):
    """ create a story """
    result = llm.invoke(state["input"])
    return {"output": result.content}


def llm_call_router(state: State):
    """ Route the input to the appropriate node """
    llm_with_tools = llm.with_structured_output(Route)
    route = llm_with_tools.invoke([
        SystemMessage(
            content="Route the input to story, joke, or poem based on the user's request."
        ),
        HumanMessage(
            content=state["input"],
        ),
    ])

    return {"decision": route.step}


def route_conditional(state: State):
    """ Route the input to the appropriate node """
    if state["decision"] == "poem":
        return llm_call_poem.__name__
    elif state["decision"] == "story":
        return llm_call_story.__name__
    elif state["decision"] == "joke":
        return llm_call_joke.__name__
    else:
        raise GraphInterrupt


if __name__ == "__main__":
    graph_builder = StateGraph(State)
    graph_builder.add_node(llm_call_router.__name__, llm_call_router)
    graph_builder.add_node(llm_call_joke.__name__, llm_call_joke)
    graph_builder.add_node(llm_call_poem.__name__, llm_call_poem)
    graph_builder.add_node(llm_call_story.__name__, llm_call_story)

    graph_builder.add_edge(START, llm_call_router.__name__)
    graph_builder.add_conditional_edges(llm_call_router.__name__, route_conditional, [
        llm_call_poem.__name__,
        llm_call_story.__name__,
        llm_call_joke.__name__,
    ])

    graph = graph_builder.compile()

    resp = graph.invoke({"input": "Write me a story about cats"})
    print(resp)
    pass
