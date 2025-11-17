from collections.abc import AsyncIterable
from typing import Any
from langchain_core.messages import AIMessage, ToolMessage
from graph import graph

class InventoryAgent:

    def __init__(self):
        # Initialize the agent with the pre-defined graph
        self.graph = graph

    # synchronous method to invoke the agent
    def invoke(self, query, sessionId) -> str:
        config = {'configurable': {'thread_id': sessionId}}
        response = self.graph.invoke({'messages': [('user', query)]}, config)
        return {
            'is_task_complete': True,
            'require_user_input': False,
            'content': response.content,
        }

    # asynchronous method to stream the agent's response
    async def stream(self, query, sessionId) -> AsyncIterable[dict[str, Any]]:
        inputs = {'messages': [('user', query)]}
        config = {'configurable': {'thread_id': sessionId}}
        final_message = None

        async for item in self.graph.astream(inputs, config, stream_mode='values'):
            message = item['messages'][-1]
            print(f"Message: {message}")
            if (
                isinstance(message, AIMessage)
                and message.tool_calls
                and len(message.tool_calls) > 0
            ):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Invoking tool...',
                }
            elif isinstance(message, ToolMessage):
                print(f"Tool response: {message.content}")
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Processing the tool response..',
                }
            else:
                print(f"Instance of message: {type(message)}")
                print(f"Instance of AImessage: {isinstance(message, AIMessage)}")
                print(f"Unidentified Message: {message.content}")
                final_message = message.content
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': message.content,
                }

        yield {
            'is_task_complete': True,
            'require_user_input': False,
            'content': 'Processing complete.' if final_message is None else final_message,
        }

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']