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


class EmailClassification(TypedDict):
    intent: Literal["question", "bug", "billing", "feature", "complex"]
    urgency: Literal["low", "medium", "high", "critical"]
    topic: str
    summary: str


class EmailAgentState(TypedDict):
    messages: list[str] | None
    email_content: str

    classification: EmailClassification | None

    search_result: list[str] | None
    reply: str | None


def read_email():
    """ 读取客户邮件，对邮件进行分类 """
    pass


def search_doc():
    """ 搜索文档 """
    pass


def generate_content_then_reply():
    """ 草拟合适的内容来回复 """
    pass


def human_agent():
    """ 复杂问题需要转给人工客服 """
    pass
