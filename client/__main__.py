import asyncio
import json
import httpx
from uuid import uuid4
# 굳이 asyncclick 필요 없어요. 일반 input으로 충분
# import asyncclick as click

from a2a.client import A2AClient, A2ACardResolver
from a2a.types import (
    TextPart,
    Task,
    Message,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    MessageSendConfiguration,
    SendStreamingMessageRequest,
    MessageSendParams,
    GetTaskRequest,
    TaskQueryParams,
    JSONRPCErrorResponse,
)
from rich.console import Console
console = Console()

BASE_URL = "http://localhost:8080"

async def main():
    async with httpx.AsyncClient(timeout=30) as httpx_client:
        # 0) 에이전트 카드 조회
        card_resolver = A2ACardResolver(httpx_client, BASE_URL)
        card = await card_resolver.get_agent_card()

        console.rule("[bold green]Agent Card")
        console.print_json(data=json.loads(card.model_dump_json(exclude_none=True)))

        # prompt = click.prompt('\nWhat do you want to send to the agent?')
        # prompt = input("\nWhat do you want to send to the agent?: ")
        client = A2AClient(httpx_client, agent_card=card)
        prompt = str({
            "user_id": "test-user-123",
            "sheet_id": "inventory-sheet-001",
            "message": "Generate a weekly inventory report for all items."
        })


        if not (card.capabilities and card.capabilities.streaming):
            print("Streaming is not supported by the agent.")
            return

        # 1) 요청 payload 구성
        user_msg = Message(
            role="user",
            parts=[TextPart(text=prompt)],
            messageId=str(uuid4()),
        )
        payload = MessageSendParams(
            id=str(uuid4()),
            message=user_msg,
            configuration=MessageSendConfiguration(
                acceptedOutputModes=["text"],
            ),
        )

        # 2) 스트림 한 번만 생성!
        response_stream = client.send_message_streaming(
            SendStreamingMessageRequest(id=str(uuid4()), params=payload)
        )

        # 3) 식별자/메시지 안전 초기화
        taskId = None
        contextId = None
        last_message = None

        # 4) 스트림 소비
        try:
            async for result in response_stream:
                root = result.root

                # JSON-RPC 에러 이벤트
                if isinstance(root, JSONRPCErrorResponse):
                    console.print("[bold red]Error:[/]", root.error)
                    return  # 미초기화 변수 접근 방지

                event = root.result
                # 식별자 업데이트
                if isinstance(event, Task):
                    taskId = event.id
                    contextId = event.contextId
                elif isinstance(event, (TaskStatusUpdateEvent, TaskArtifactUpdateEvent)):
                    taskId = event.taskId
                    contextId = event.contextId
                elif isinstance(event, Message):
                    last_message = event

                # 보기 좋게 출력
                console.print(
                    "[cyan]stream event =>[/]",
                    json.loads(event.model_dump_json(exclude_none=True)),
                )

        except httpx.HTTPError as e:
            console.print(f"[bold red]Stream failed:[/] {e}")
            return

        # 5) 스트림 종료 후 Task 상세 조회 (있을 때만)
        if taskId:
            try:
                task_resp = await client.get_task(
                    GetTaskRequest(id=str(uuid4()), params=TaskQueryParams(id=taskId))
                )
                task_obj = task_resp.root.result
                console.rule("[bold yellow]Task Result")
                console.print_json(data=json.loads(task_obj.model_dump_json(exclude_none=True)))
            except httpx.HTTPError as e:
                console.print(f"[bold red]GetTask failed:[/] {e}")
        else:
            console.print("[bold yellow]No taskId captured from stream.[/]")
"""
{
  "artifacts": [
    {
      "artifactId": "db30c626-7d4e-4773-881c-72ea5980da8b",
      "name": "conversion_result",
      "parts": [
        {
          "kind": "text",
          "text": "Here’s the inventory report for the past week:\n\n- **Low‑stock items:** 2  \n- **Restocks performed:** 10  \n\nLet me know if you’d like more details (e.g., item‑level breakdown, forecast, or alerts for any thresholds)."
        }
      ]
    }
  ],
  "contextId": "522396a1-605f-4be7-b043-234a26e2662f",
  "history": [
    {
      "contextId": "522396a1-605f-4be7-b043-234a26e2662f",
      "kind": "message",
      "messageId": "8a2f30ec-e642-470e-9e43-83b3ba05556b",
      "parts": [
        {
          "kind": "text",
          "text": "{'user_id': 'test-user-123', 'sheet_id': 'inventory-sheet-001', 'message': 'Generate a weekly inventory report for all items.'}"
        }
      ],
      "role": "user",
      "taskId": "f13c51e4-c719-49d6-b45a-c3577c2f801c"
    },
    {
      "contextId": "522396a1-605f-4be7-b043-234a26e2662f",
      "kind": "message",
      "messageId": "32c18a38-52b6-4827-8f1d-6dde4dedbece",
      "parts": [
        {
          "kind": "text",
          "text": "Thinking..."
        }
      ],
      "role": "agent",
      "taskId": "f13c51e4-c719-49d6-b45a-c3577c2f801c"
    },
    {
      "contextId": "522396a1-605f-4be7-b043-234a26e2662f",
      "kind": "message",
      "messageId": "fc40b096-8148-4bd7-b62f-e6feea9b1148",
      "parts": [
        {
          "kind": "text",
          "text": "{'user_id': 'test-user-123', 'sheet_id': 'inventory-sheet-001', 'message': 'Generate a weekly inventory report for all items.'}"
        }
      ],
      "role": "agent",
      "taskId": "f13c51e4-c719-49d6-b45a-c3577c2f801c"
    },
    {
      "contextId": "522396a1-605f-4be7-b043-234a26e2662f",
      "kind": "message",
      "messageId": "873ba7fa-c2cb-4d10-93d6-ab054c64f1e8",
      "parts": [
        {
          "kind": "text",
          "text": "Invoking tool..."
        }
      ],
      "role": "agent",
      "taskId": "f13c51e4-c719-49d6-b45a-c3577c2f801c"
    },
    {
      "contextId": "522396a1-605f-4be7-b043-234a26e2662f",
      "kind": "message",
      "messageId": "811c5dc2-b254-4835-a267-e11b59687dc6",
      "parts": [
        {
          "kind": "text",
          "text": "Processing the tool response.."
        }
      ],
      "role": "agent",
      "taskId": "f13c51e4-c719-49d6-b45a-c3577c2f801c"
    },
    {
      "contextId": "522396a1-605f-4be7-b043-234a26e2662f",
      "kind": "message",
      "messageId": "32429c13-ead8-442e-9db1-5508dbaa8109",
      "parts": [
        {
          "kind": "text",
          "text": "Here’s the inventory report for the past week:\n\n- **Low‑stock items:** 2  \n- **Restocks performed:** 10  \n\nLet me know if you’d like more details (e.g., item‑level breakdown, forecast, or alerts for any thresholds)."
        }
      ],
      "role": "agent",
      "taskId": "f13c51e4-c719-49d6-b45a-c3577c2f801c"
    }
  ],
  "id": "f13c51e4-c719-49d6-b45a-c3577c2f801c",
  "kind": "task",
  "status": {
    "state": "completed",
    "timestamp": "2025-11-10T13:49:10.483277+00:00"
  }
}
"""
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
