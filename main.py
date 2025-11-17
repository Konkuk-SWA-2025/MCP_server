import click
import httpx

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    InMemoryTaskStore,
    InMemoryPushNotificationConfigStore,
    BasePushNotificationSender,
)
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from agent import InventoryAgent
from agent_executor import InventoryAgentExecutor

def app(host: str = None, port: int = None) -> A2AStarletteApplication:
    """Creates and returns the A2AStarletteApplication instance."""
    url = f"http://{host}:{port}"

    # 푸시를 쓸 계획이면 True로
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

    skill = AgentSkill(
        id="inventory_management",
        name="Inventory Management",
        description="Query inventory, adjust stock, request forecasts, check thresholds, send alerts, and generate reports.",
        tags=["inventory", "stock", "forecast", "alerts"],
        examples=[
            "query inventory for item-001",
            "decrease stock for item-002 by 5",
            "request forecast for item-001 for 30 days",
            "check thresholds for item-002",
            "generate weekly inventory report",
        ],
    )

    agent_card = AgentCard(
        name="Inventory Agent",
        description="An agent that manages and reports on inventory.",
        url=url,
        version="1.0.0",
        defaultInputModes=InventoryAgent.SUPPORTED_CONTENT_TYPES,
        defaultOutputModes=InventoryAgent.SUPPORTED_CONTENT_TYPES,
        capabilities=capabilities,
        skills=[skill],
    )

    httpx_client = httpx.AsyncClient()
    push_config_store = InMemoryPushNotificationConfigStore()
    push_sender = BasePushNotificationSender(
        httpx_client=httpx_client, config_store=push_config_store
    )

    request_handler = DefaultRequestHandler(
        agent_executor=InventoryAgentExecutor(),
        task_store=InMemoryTaskStore(),
        push_config_store=push_config_store,  
        push_sender=push_sender,              
    )

    server = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    return server.build()

@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=8080)
def main(host, port):
    """Starts the Weather Agent server."""
    try:
        agent_app = app(host, port)
        import uvicorn
        uvicorn.run(agent_app, host=host, port=port)
    except Exception as e:
        print(f"An error occurred during server startup: {e}")
        raise

if __name__ == "__main__":
    main()
