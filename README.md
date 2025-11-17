# Agent-Server

**간단한 소개:**
- **프로젝트:** `Agent-Server` — 간단한 재고 관리 에이전트(Inventory Agent)와 MCP(Model Context Protocol) 기반 도구들의 데모 서버
- **목적:** LangGraph / LangChain 계열 라이브러리와 MCP 툴/리소스를 사용해 재고 조회, 재고 조정, 예측, 알림, 리포트 생성 등의 워크플로우를 시연합니다.

**주요 기능:**
- **에이전트:** `mcp_a2a/agent.py`에 정의된 `InventoryAgent`는 LangGraph 그래프를 사용해 사용자 질의에 응답합니다.
- **서버:** `mcp_a2a/main.py`는 A2A(Agent-to-Agent) 스타일의 ASGI 서버 진입점을 제공합니다 (UVicorn 사용).
- **도구(툴) 및 리소스:** `mcp_a2a/mcp_server.py`는 MCP 툴(예: `get_item`, `adjust_stock`, `generate_forecast`, `check_thresholds`, `send_alert`, `generate_report`)과 `inventory://{item_id}` 리소스를 제공합니다.

**빠른 시작 (Windows - cmd.exe):**
- **1) 가상환경 생성 (권장)**

```bat
python -m venv .venv
.venv\Scripts\activate
```

- **2) 의존성 설치**

```bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

- **3) 서버 실행**

```bat
python main.py --host localhost --port 8080
```

**파일/폴더 요약:**
- **`mcp_a2a/`**: 핵심 구현
  - **`main.py`**: ASGI 앱 생성 및 UVicorn 실행 진입점
  - **`agent.py`**: `InventoryAgent` (동기/스트리밍 인터페이스)
  - **`agent_executor.py`**: A2A 프레임워크용 `AgentExecutor` 구현
  - **`mcp_server.py`**: MCP 툴 및 리소스 정의(로컬 테스트용 샘플 데이터 포함)
  - **`graph.py`**: LangGraph 상태 그래프 및 모델 바인딩

