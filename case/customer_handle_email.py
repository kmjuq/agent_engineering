"""
这个智能助手需要做到以下几点：

- 读取客户发来的邮件
- 按紧急程度和问题类型分类
- 查找相关文档来解答疑问
- 草拟合适的回复内容
- 把复杂问题转给人工客服
- 需要的时候安排后续跟进

需要处理的例子场景：

1. 简单产品问题："怎么重置密码？"
2. 报Bug："选PDF格式导出时，程序会崩溃"
3. 紧急账单问题："我的订阅被重复扣费了！"
4. 功能建议："手机App能不能加个夜间模式？"
5. 复杂技术问题："我们的API集成时不时报504错误"
"""
from typing import TypedDict, Literal

from langchain_core.messages import HumanMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END, START
from langgraph.func import task, entrypoint
from langgraph.graph import StateGraph
from langgraph.types import Command, interrupt, RetryPolicy

from utils.std_model import base_model

llm = base_model()


class EmailClassification(TypedDict):
    intent: Literal["question", "bug", "billing", "feature", "complex"]
    urgency: Literal["low", "medium", "high", "critical"]
    topic: str
    summary: str


class EmailAgentState(TypedDict):
    messages: list[str] | None
    email_content: str

    classification: EmailClassification | None

    search_results: list[str] | None
    draft_resp_content: str | None


def read_email(state: EmailAgentState) -> dict:
    """ 抽取和解析邮件内容 """
    return {
        "messages": [
            HumanMessage(content=f"处理邮件：{state['email_content']}"),
        ]
    }


def classify(state: EmailAgentState) -> Command[
    Literal["search_doc", "human_review", "bug_report", "draft_resp_content"]]:
    """ 使用大模型给邮件内容分类意图和紧急程度，然后路由到 """
    classify_llm = llm.with_structured_output(EmailClassification)

    classify_prompt = f"""
    分析邮件内容，并将其分类：
    
    Email: {state['email_content']}
    
    Provide classification including intent, urgency, topic, and summary.
    """

    classification = classify_llm.invoke(classify_prompt)

    if classification["intent"] == "billing" or classification["urgency"] == "critical":
        goto = "human_review"
    elif classification["intent"] in ["question", "feature"]:
        goto = "search_doc"
    elif classification["intent"] == "bug":
        goto = "bug_report"
    else:
        goto = "draft_resp_content"

    return Command(
        update={
            "classification": classification,
        },
        goto=goto,
    )


def search_doc(state: EmailAgentState) -> Command[Literal["draft_resp_content"]]:
    """ 搜索知识库相关文档信息 """
    # Build search query from classification
    classification = state.get('classification', {})
    query = f"{classification.get('intent', '')} {classification.get('topic', '')}"

    try:
        # Implement your search logic here
        # Store raw search results, not formatted text
        search_results = [
            "Reset password via Settings > Security > Change Password",
            "Password must be at least 12 characters",
            "Include uppercase, lowercase, numbers, and symbols"
        ]
    except Exception as e:
        # For recoverable search errors, store error and continue
        search_results = [f"Search temporarily unavailable: {str(e)}"]

    return Command(
        update={"search_results": search_results},  # Store raw results or error
        goto="draft_resp_content"
    )


def send_reply(state: EmailAgentState) -> dict:
    """Send the email response"""
    # Integrate with email service
    print(f"Sending reply: {state['draft_resp_content'][:100]}...")
    return {}


def draft_resp_content(state: EmailAgentState) -> Command[Literal["human_review", "send_reply"]]:
    """Generate response using context and route based on quality"""

    classification = state.get('classification', {})

    # Format context from raw state data on-demand
    context_sections = []

    if state.get('search_results'):
        # Format search results for the prompt
        formatted_docs = "\n".join([f"- {doc}" for doc in state['search_results']])
        context_sections.append(f"Relevant documentation:\n{formatted_docs}")

    # Build the prompt with formatted context
    draft_prompt = f"""
        Draft a response to this customer email:
        {state['email_content']}

        Email intent: {classification.get('intent', 'unknown')}
        Urgency level: {classification.get('urgency', 'medium')}

        {chr(10).join(context_sections)}

        Guidelines:
        - Be professional and helpful
        - Address their specific concern
        - Use the provided documentation when relevant
        """

    response = llm.invoke(draft_prompt)

    # Determine if human review needed based on urgency and intent
    needs_review = (
            classification.get('urgency') in ['high', 'critical'] or
            classification.get('intent') == 'complex'
    )

    # Route to appropriate next node
    goto = "human_review" if needs_review else "send_reply"

    return Command(
        update={"draft_resp_content": response.content},  # Store only the raw response
        goto=goto
    )
    pass


def human_review(state: EmailAgentState) -> Command[Literal["send_reply", END]]:
    """Pause for human review using interrupt and route based on decision"""

    classification = state.get('classification', {})

    # interrupt() must come first - any code before it will re-run on resume
    human_decision = interrupt({
        "original_email": state.get('email_content', ''),
        "draft_resp_content": state.get('draft_resp_content', ''),
        "urgency": classification.get('urgency'),
        "intent": classification.get('intent'),
        "action": "Please review and approve/edit this response"
    })

    # Now process the human's decision
    if human_decision.get("approved"):
        return Command(
            update={"draft_resp_content": human_decision.get("edited_response", state.get('draft_resp_content', ''))},
            goto="send_reply"
        )
    else:
        # Rejection means human will handle directly
        return Command(update={}, goto=END)


def bug_report(state: EmailAgentState) -> Command[Literal["draft_resp_content"]]:
    """ 创建或更新bug追踪工单"""

    ticket_id = "BUG-12345"
    return Command(
        update={
            "search_results": [f"Bug ticket {ticket_id} created"],
            "current_step": "bug_tracked"
        },
        goto="draft_resp_content"
    )


if __name__ == "__main__":
    # Create the graph
    workflow = StateGraph(EmailAgentState)

    workflow.add_node("read_email", read_email)
    workflow.add_node("classify", classify)
    workflow.add_node("search_doc", search_doc, retry_policy=RetryPolicy(max_attempts=3))
    workflow.add_node("bug_report", bug_report)
    workflow.add_node("draft_resp_content", draft_resp_content)
    workflow.add_node("human_review", human_review)
    workflow.add_node("send_reply", send_reply)

    # Add only the essential edges
    workflow.add_edge(START, "read_email")
    workflow.add_edge("read_email", "classify")
    workflow.add_edge("send_reply", END)

    # Compile with checkpointer for persistence, in case run graph with Local_Server --> Please compile without checkpointer
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)




