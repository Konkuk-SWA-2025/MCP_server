import asyncio
from typing_extensions import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_ollama.chat_models import ChatOllama
from langchain_mcp_adapters.client import MultiServerMCPClient

# mcp_server.py가 실행될 주소
MCP_URL = "http://localhost:8000/mcp"  
# 사용할 모델 (Ollama)
MODEL = "llama3.2" # 혹은 가지고 계신 모델 이름

client = MultiServerMCPClient({
    "remote": {"transport": "streamable_http", "url": MCP_URL}
    })

def _load_tools_sync():
    async def _load():
        return await client.get_tools()
    return asyncio.run(_load())

tools = _load_tools_sync()

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

# 시스템 프롬프트: sheet_id를 모르면 물어보거나 기본값을 쓰도록 유도
system_prompt = (
    "You are an Inventory Manager AI. "
    "You have access to tools that manipulate real Google Sheets and Database records. "
    "Use 'get_item_stock', 'adjust_stock', 'predict_depletion', 'check_thresholds'. "
    "Important: If a tool requires a 'sheet_id' and the user hasn't provided one, "
    "you can try omitting it to use the system default, or ask the user for it if it fails. "
    "Always confirm the result of the tool execution to the user."
)

def chatbot(state: State) -> State:
    model = ChatOllama(model=MODEL, temperature=0.0).bind_tools(tools)
    
    # 시스템 메시지를 대화 내역 맨 앞에 추가
    priming = [SystemMessage(content=system_prompt)]
    full_history = priming + state["messages"]

    response = model.invoke(full_history)     
    return {"messages": [response]}

builder = StateGraph(State)
builder.add_node("chatbot", chatbot)
builder.add_node("tools", ToolNode(tools))

builder.add_edge(START, "chatbot")
builder.add_conditional_edges("chatbot", tools_condition)
builder.add_edge("tools", "chatbot")
builder.add_edge("chatbot", END)

graph = builder.compile()