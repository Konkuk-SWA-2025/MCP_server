import os
import asyncio
import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing_extensions import TypedDict, Annotated
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_ollama.chat_models import ChatOllama
from langchain_mcp_adapters.client import MultiServerMCPClient

# --- 설정 로드 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Orchestrator")
load_dotenv()

MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.2") # Ollama 모델 이름

# --- MCP Client 초기화 (도구 로드) ---
try:
    client = MultiServerMCPClient({"remote": {"transport": "streamable_http", "url": MCP_URL}})
    def _load_tools_sync():
        async def _load():
            try:
                return await client.get_tools()
            except Exception as e:
                logger.error(f"FATAL: Cannot connect to MCP server at {MCP_URL}. Is mcp_server.py running?")
                return []
        return asyncio.run(_load())
    tools = _load_tools_sync()
    if not tools:
        raise RuntimeError("No tools loaded from MCP server.")
except Exception as e:
    logger.error(f"Failed to initialize MCP Client: {e}")
    tools = []

# --- LangGraph 정의 (Agent-Server의 graph.py 로직) ---
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

system_prompt = (
    "You are an Inventory Manager AI. Use the provided tools to answer the user's request. "
    "The user's message will contain their 'sheet_id' and 'user_id' in parentheses. "
    "You MUST pass the correct 'sheet_id' argument when calling any tool."
    "Do not ask for the sheet_id, it is provided. "
    "Tool names are in Korean. (예: 재고_조회툴, 입출고_기록툴)"
)

def chatbot(state: State) -> State:
    model = ChatOllama(model=MODEL_NAME, temperature=0.0).bind_tools(tools)
    priming = [SystemMessage(content=system_prompt)]
    response = model.invoke(priming + state["messages"])     
    return {"messages": [response]}

builder = StateGraph(State)
builder.add_node("chatbot", chatbot)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "chatbot")
builder.add_conditional_edges("chatbot", tools_condition)
builder.add_edge("tools", "chatbot")
graph = builder.compile()

# --- FastAPI 서버 정의 ---
app = FastAPI(title="Agent Orchestrator")

class AgentRequest(BaseModel):
    user_id: str
    channel_id: str
    sheet_id: str
    message: str

# 세션(대화) 기록
sessions = {}

@app.post("/")
async def handle_request(payload: AgentRequest):
    """
    IngressAPI로부터 요청을 받아 LangGraph를 실행하고 응답 반환
    (A2A 프로토콜 대신 일반 HTTP/JSON 사용)
    """
    session_id = payload.user_id # 세션 ID로 user_id 사용
    
    # LLM이 sheet_id와 user_id를 인식하도록 메시지 보강
    augmented_message = f"""
    (System Info: user_id='{payload.user_id}', sheet_id='{payload.sheet_id}')
    User Message: {payload.message}
    """
    
    inputs = {'messages': [HumanMessage(content=augmented_message)]}
    config = {'configurable': {'thread_id': session_id}}
    
    try:
        # LangGraph 실행
        # astream 대신 invoke를 사용하여 최종 응답만 받음
        response_state = graph.invoke(inputs, config)
        
        # 마지막 AI 메시지를 응답으로 반환
        final_message = response_state['messages'][-1].content
        
        logger.info(f"Orchestrator response for {payload.user_id}: {final_message}")
        return {"response": final_message}
        
    except Exception as e:
        logger.error(f"Orchestration error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# --- 실행 (Port 8080) ---
if __name__ == "__main__":
    logger.info("Starting Agent Orchestrator Server on port 8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080)