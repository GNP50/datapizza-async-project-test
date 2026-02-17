"""
Custom datapizza Client wrapper for Ollama Cloud API

This provides the same interface as OpenAILikeClient but uses Ollama's native API.
"""
from collections.abc import AsyncIterator, Iterator
from typing import Literal, Optional
import json
import base64

import ollama
from datapizza.core.cache import Cache
from datapizza.core.clients import Client, ClientResponse
from datapizza.core.clients.models import TokenUsage
from datapizza.memory import Memory
from datapizza.tools.tools import Tool
from datapizza.type import (
    FunctionCallBlock,
    Model,
    StructuredBlock,
    TextBlock,
)
from datapizza.clients.openai_like.memory_adapter import OpenAILikeMemoryAdapter

from .base_image_client import BaseImageClient


class OllamaDatapizzaClient(BaseImageClient):
    """
    A datapizza Client for Ollama Cloud API using the native Ollama client.

    This provides the same interface as OpenAILikeClient but works with Ollama's
    native API instead of the OpenAI-compatible endpoints.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-oss:120b-cloud",
        system_prompt: str = "",
        temperature: float | None = None,
        cache: Cache | None = None,
        base_url: str = "https://api.ollama.com",
    ):
        if temperature and not 0 <= temperature <= 2:
            raise ValueError("Temperature must be between 0 and 2")

        super().__init__(
            model_name=model,
            system_prompt=system_prompt,
            temperature=temperature,
            cache=cache,
        )

        self.base_url = base_url
        self.api_key = api_key
        self.memory_adapter = OpenAILikeMemoryAdapter()
        self._set_client()

    def _set_client(self):
        """Initialize the synchronous Ollama client"""
        if not self.client:
            self.client = ollama.Client(
                host=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"}
            )

    def _set_a_client(self):
        """Initialize the asynchronous Ollama client.
        Always recreate to avoid 'Event loop is closed' errors in Celery tasks."""
        self.a_client = ollama.AsyncClient(
            host=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"}
        )

    def _convert_blocks_to_string(self, content) -> str:
        """Convert TextBlock or list of blocks to string"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Extract text from TextBlock objects
            text_parts = []
            for block in content:
                if hasattr(block, "content"):
                    text_parts.append(block.content)
                elif isinstance(block, str):
                    text_parts.append(block)
            return "\n".join(text_parts)
        elif hasattr(content, "content"):
            return content.content
        else:
            return str(content)

    def _messages_from_memory(
        self,
        system_prompt: str | None,
        input: str | list,
        memory: Memory | None
    ) -> list[dict]:
        """Convert memory and input to Ollama message format"""
        messages = []

        # Add system prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Add memory messages if any
        if memory:
            for turn in memory.get_all():
                # Add user message
                if turn.input:
                    user_content = self._convert_blocks_to_string(turn.input)
                    messages.append({"role": "user", "content": user_content})

                # Add assistant message
                if turn.output:
                    assistant_content = self._convert_blocks_to_string(turn.output)
                    messages.append({"role": "assistant", "content": assistant_content})

        # Add the current input
        input_text = self._convert_blocks_to_string(input)
        messages.append({"role": "user", "content": input_text})

        return messages

    def _token_usage_from_response(self, response) -> TokenUsage:
        """Extract token usage from Ollama response"""
        # Ollama doesn't always provide detailed token counts
        prompt_eval_count = getattr(response, "prompt_eval_count", 0) or 0
        eval_count = getattr(response, "eval_count", 0) or 0

        return TokenUsage(
            prompt_tokens=prompt_eval_count,
            completion_tokens=eval_count,
            cached_tokens=0,
        )

    def _response_to_client_response(self, response) -> ClientResponse:
        """Convert Ollama response to ClientResponse"""
        content = response.get("message", {}).get("content", "") if isinstance(response, dict) else response.message.content

        blocks = [TextBlock(content=content)]

        # Handle tool calls if present
        tool_calls = response.get("message", {}).get("tool_calls") if isinstance(response, dict) else getattr(response.message, "tool_calls", None)
        if tool_calls:
            # TODO: Implement tool call handling for Ollama
            pass

        token_usage = self._token_usage_from_response(response)
        done_reason = response.get("done_reason") if isinstance(response, dict) else getattr(response, "done_reason", None)

        return ClientResponse(
            content=blocks,
            stop_reason=done_reason,
            usage=token_usage,
        )

    def _invoke(
        self,
        *,
        input: str,
        tools: list[Tool] | None,
        memory: Memory | None,
        tool_choice: Literal["auto", "required", "none"] | list[str],
        temperature: float | None,
        max_tokens: int,
        system_prompt: str | None,
        **kwargs,
    ) -> ClientResponse:
        """Synchronous invocation"""
        messages = self._messages_from_memory(system_prompt or self.system_prompt, input, memory)

        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens:
            options["num_predict"] = max_tokens

        client = self._get_client()
        response = client.chat(
            model=self.model_name,
            messages=messages,
            stream=False,
            options=options if options else None,
            **kwargs
        )

        return self._response_to_client_response(response)

    async def _a_invoke(
        self,
        *,
        input: str,
        tools: list[Tool] | None,
        memory: Memory | None,
        tool_choice: Literal["auto", "required", "none"] | list[str],
        temperature: float | None,
        max_tokens: int,
        system_prompt: str | None,
        **kwargs,
    ) -> ClientResponse:
        """Asynchronous invocation"""
        messages = self._messages_from_memory(system_prompt or self.system_prompt, input, memory)

        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens:
            options["num_predict"] = max_tokens

        a_client = self._get_a_client()
        response = await a_client.chat(
            model=self.model_name,
            messages=messages,
            stream=False,
            options=options if options else None,
            **kwargs
        )

        return self._response_to_client_response(response)

    def _stream_invoke(
        self,
        input: str,
        tools: list[Tool] | None,
        memory: Memory | None,
        tool_choice: Literal["auto", "required", "none"] | list[str],
        temperature: float | None,
        max_tokens: int,
        system_prompt: str | None,
        **kwargs,
    ) -> Iterator[ClientResponse]:
        """Streaming invocation"""
        messages = self._messages_from_memory(system_prompt or self.system_prompt, input, memory)

        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens:
            options["num_predict"] = max_tokens

        client = self._get_client()
        stream = client.chat(
            model=self.model_name,
            messages=messages,
            stream=True,
            options=options if options else None,
            **kwargs
        )

        accumulated_content = ""
        usage = TokenUsage()

        for chunk in stream:
            if isinstance(chunk, dict):
                delta = chunk.get("message", {}).get("content", "")
            else:
                delta = chunk.message.content if chunk.message else ""

            accumulated_content += delta

            # Update usage if available
            if isinstance(chunk, dict):
                if chunk.get("done"):
                    usage = self._token_usage_from_response(chunk)
            else:
                if getattr(chunk, "done", False):
                    usage = self._token_usage_from_response(chunk)

            yield ClientResponse(
                content=[TextBlock(content=accumulated_content)],
                delta=delta,
                stop_reason=None,
            )

        # Final response with usage
        yield ClientResponse(
            content=[TextBlock(content=accumulated_content)],
            stop_reason="stop",
            usage=usage,
        )

    async def _a_stream_invoke(
        self,
        input: str,
        tools: list[Tool] | None = None,
        memory: Memory | None = None,
        tool_choice: Literal["auto", "required", "none"] | list[str] = "auto",
        temperature: float | None = None,
        max_tokens: int | None = None,
        system_prompt: str | None = None,
        **kwargs,
    ) -> AsyncIterator[ClientResponse]:
        """Async streaming invocation"""
        messages = self._messages_from_memory(system_prompt or self.system_prompt, input, memory)

        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens:
            options["num_predict"] = max_tokens

        a_client = self._get_a_client()
        stream = await a_client.chat(
            model=self.model_name,
            messages=messages,
            stream=True,
            options=options if options else None,
            **kwargs
        )

        accumulated_content = ""
        usage = TokenUsage()

        async for chunk in stream:
            if isinstance(chunk, dict):
                delta = chunk.get("message", {}).get("content", "")
            else:
                delta = chunk.message.content if chunk.message else ""

            accumulated_content += delta

            # Update usage if available
            if isinstance(chunk, dict):
                if chunk.get("done"):
                    usage = self._token_usage_from_response(chunk)
            else:
                if getattr(chunk, "done", False):
                    usage = self._token_usage_from_response(chunk)

            yield ClientResponse(
                content=[TextBlock(content=accumulated_content)],
                delta=delta,
                stop_reason=None,
            )

        # Final response with usage
        yield ClientResponse(
            content=[TextBlock(content=accumulated_content)],
            stop_reason="stop",
            usage=usage,
        )

    def _structured_response(
        self,
        input: str,
        output_cls: type[Model],
        memory: Memory | None,
        temperature: float | None,
        max_tokens: int,
        system_prompt: str | None,
        tools: list[Tool] | None,
        tool_choice: Literal["auto", "required", "none"] | list[str] = "auto",
        **kwargs,
    ) -> ClientResponse:
        """Structured response - not fully supported by Ollama"""
        # For now, we'll use regular invoke and try to parse JSON
        # Ollama doesn't have native structured output support
        raise NotImplementedError("Structured responses not yet implemented for Ollama")

    async def _a_structured_response(
        self,
        input: str,
        output_cls: type[Model],
        memory: Memory | None,
        temperature: float,
        max_tokens: int,
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        tool_choice: Literal["auto", "required", "none"] | list[str] = "auto",
        **kwargs,
    ):
        """Async structured response - not fully supported by Ollama"""
        raise NotImplementedError("Structured responses not yet implemented for Ollama")

    def _convert_tool_choice(
        self, tool_choice: Literal["auto", "required", "none"] | list[str]
    ) -> dict | Literal["auto", "required", "none"]:
        """Convert tool choice to Ollama format"""
        # Ollama doesn't support tool choice in the same way as OpenAI
        # For now, just return the tool_choice as-is
        return tool_choice

    def _embed(self, input: str | list[str], **kwargs) -> list[list[float]]:
        """Embedding not implemented for Ollama chat client"""
        raise NotImplementedError("Embedding not implemented for OllamaDatapizzaClient")

    async def _a_embed(self, input: str | list[str], **kwargs) -> list[list[float]]:
        """Async embedding not implemented for Ollama chat client"""
        raise NotImplementedError("Embedding not implemented for OllamaDatapizzaClient")

    def call_ocr(
        self,
        image_b64: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> ClientResponse:
        """
        Extract text from an image using Ollama's native vision API.

        Args:
            image_b64: Base64-encoded image string
            prompt: Text prompt for the OCR task
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ClientResponse with extracted text
        """
        # Convert base64 string to bytes for Ollama
        image_bytes = base64.b64decode(image_b64)

        # Prepare message with native Ollama images parameter
        messages = [
            {
                "role": "user",
                "content": prompt,
                "images": [image_bytes]
            }
        ]

        # Prepare options
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens:
            options["num_predict"] = max_tokens

        # Make the API call
        client = self._get_client()
        response = client.chat(
            model=self.model_name,
            messages=messages,
            stream=False,
            options=options if options else None,
        )

        return self._response_to_client_response(response)

    async def a_call_ocr(
        self,
        image_b64: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> ClientResponse:
        """
        Async version: Extract text from an image using Ollama's native vision API.

        Args:
            image_b64: Base64-encoded image string
            prompt: Text prompt for the OCR task
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ClientResponse with extracted text
        """
        # Convert base64 string to bytes for Ollama
        image_bytes = base64.b64decode(image_b64)

        # Prepare message with native Ollama images parameter
        messages = [
            {
                "role": "user",
                "content": prompt,
                "images": [image_bytes]
            }
        ]

        # Prepare options
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens:
            options["num_predict"] = max_tokens

        # Make the async API call
        a_client = self._get_a_client()
        response = await a_client.chat(
            model=self.model_name,
            messages=messages,
            stream=False,
            options=options if options else None,
        )

        return self._response_to_client_response(response)
    