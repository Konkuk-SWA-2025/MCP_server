import logging
import traceback
from typing_extensions import override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    InvalidParamsError,
    Part,
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError

from agent import InventoryAgent

logger = logging.getLogger(__name__)

class InventoryAgentExecutor(AgentExecutor):
    """Inventory AgentExecutor."""

    def __init__(self):
        self.agent = InventoryAgent()

    def _validate_request(self, context: RequestContext) -> bool:
        # 잘못된 요청일 경우 True를 리턴하도록 구현하고, 지금은 통과
        return False

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # 0) 유효성
        if self._validate_request(context):
            raise ServerError(error=InvalidParamsError())

        # 1) Task 이벤트 먼저 전송(스트림을 연다)
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)  # ← 반드시 await

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        try:
            # 2) 시작 상태 한 번 전송(스트림 유지/확인용)
            await updater.update_status(
                TaskState.working,
                new_agent_text_message("Thinking...", task.contextId, task.id),
            )

            # 3) 본 작업: LangGraph/LLM 스트리밍
            query = context.get_user_input()
            async for item in self.agent.stream(query, task.contextId):
                is_task_complete = item.get("is_task_complete", False)
                content = item.get("content", "")

                if not is_task_complete:
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(content, task.contextId, task.id),
                    )
                else:
                    await updater.add_artifact(
                        [Part(root=TextPart(text=content))],
                        name="conversion_result",
                        last_chunk=True,
                    )
                    await updater.complete()
                    break

        except Exception as e:
            traceback.print_exc()
            logger.error("An error occurred while streaming the response: %s", e)
            # (원하면 실패 상태 이벤트도 보낼 수 있음)
            # await updater.update_status(TaskState.failed, new_agent_text_message("Error", task.contextId, task.id))
            raise ServerError(error=InternalError()) from e

    @override
    async def cancel(self, request: RequestContext, event_queue: EventQueue) -> Task | None:
        raise ServerError(error=UnsupportedOperationError())
