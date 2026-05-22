from IPython.core.display_functions import display

from utils.std_model import base_model

chatLLM = base_model()
from langchain_core.prompts import ChatPromptTemplate
from IPython.core.display import HTML
from langchain_core.output_parsers import StrOutputParser

prompt_extract = ChatPromptTemplate.from_template("从以下文本中提取技术规格：\n\n{text_input}")
prompt_transform = ChatPromptTemplate.from_template(
    "将以下规格转换为 JSON 对象，使用 'cpu'、'memory' 和 'storage' 作为键：\n\n{specifications}"
)
extraction_chain = prompt_extract | chatLLM | StrOutputParser()

full_chain = (
    {"specifications": extraction_chain}
    | prompt_transform
    | chatLLM
    | StrOutputParser()
)
input_text = "新款笔记本电脑型号配备 3.5 GHz 八核处理器、16GB 内存和 1TB NVMe 固态硬盘。"

final_result = full_chain.invoke({"text_input": input_text})

print(final_result)