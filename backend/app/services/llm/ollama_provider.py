from typing import AsyncIterator
from .base import LLMProvider
from .ollama_datapizza_client import OllamaDatapizzaClient


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "gpt-oss:120b-cloud", base_url: str = "https://api.ollama.com", api_key: str | None = None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

        # Use the custom OllamaDatapizzaClient
        if api_key:
            self.client = OllamaDatapizzaClient(
                api_key=api_key,
                model=model,
                base_url=base_url
            )
        else:
            raise ValueError("Ollama API key is required for OllamaDatapizzaClient")

    async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        # Use datapizza client's invoke method
        response = await self.client.a_invoke(
            input=prompt,
            system_prompt=system_prompt,
            tools=None,
            memory=None,
            tool_choice="auto",
            temperature=kwargs.get("temperature"),
            max_tokens=kwargs.get("max_tokens", 0),
        )

        # Extract text from ClientResponse
        if response.content and len(response.content) > 0:
            return response.content[0].content
        return ""

    async def generate_stream(
        self, prompt: str, system_prompt: str | None = None, **kwargs
    ) -> AsyncIterator[str]:
        # Use datapizza client's streaming method
        stream = self.client.a_stream_invoke(
            input=prompt,
            system_prompt=system_prompt,
            tools=None,
            memory=None,
            tool_choice="auto",
            temperature=kwargs.get("temperature"),
            max_tokens=kwargs.get("max_tokens", 0),
        )

        async for response in stream:
            # Yield the delta content from each chunk
            if response.delta:
                yield response.delta

    async def generate_with_context(
        self,
        prompt: str,
        context: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs
    ) -> str:
        # Convert context to datapizza Memory format
        from datapizza.memory import Memory, MemoryTurn
        from datapizza.type import TextBlock

        memory = Memory()

        # Process context pairs (user, assistant)
        i = 0
        while i < len(context):
            user_msg = context[i]
            assistant_msg = context[i + 1] if i + 1 < len(context) else None

            if user_msg.get("role") == "user":
                user_input = [TextBlock(content=user_msg["content"])]
                assistant_output = [TextBlock(content=assistant_msg["content"])] if assistant_msg and assistant_msg.get("role") == "assistant" else []

                memory.add_turn(MemoryTurn(
                    input=user_input,
                    output=assistant_output
                ))

                i += 2 if assistant_msg else 1
            else:
                i += 1

        # Use datapizza client with memory
        response = await self.client.a_invoke(
            input=prompt,
            system_prompt=system_prompt,
            tools=None,
            memory=memory,
            tool_choice="auto",
            temperature=kwargs.get("temperature"),
            max_tokens=kwargs.get("max_tokens", 0),
        )

        # Extract text from ClientResponse
        if response.content and len(response.content) > 0:
            return response.content[0].content
        return ""
