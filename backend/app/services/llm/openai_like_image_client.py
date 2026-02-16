"""
OpenAI-Like Image Client - OpenAI-compatible client with vision/OCR capabilities

This client extends OpenAILikeClient with proper OCR support using the OpenAI Vision API format.
It works with any OpenAI-compatible API that supports vision (GPT-4o, GPT-4 Turbo with Vision, etc.).
"""
from typing import Optional, Literal
import httpx
from datapizza.core.cache import Cache
from datapizza.core.clients import ClientResponse
from datapizza.memory import Memory
from datapizza.tools.tools import Tool
from datapizza.clients.openai_like import OpenAILikeClient

from .base_image_client import BaseImageClient


class OpenAILikeImageClient(BaseImageClient, OpenAILikeClient):
    """
    OpenAI-compatible client with vision support.

    Extends OpenAILikeClient with proper call_ocr() implementations that send
    images using the OpenAI Vision API format.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        system_prompt: str = "",
        temperature: float | None = None,
        cache: Cache | None = None,
        base_url: str | httpx.URL | None = None,
    ):
        # Call parent class constructors
        OpenAILikeClient.__init__(
            self,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            cache=cache,
            base_url=base_url,
        )

    def call_ocr(
        self,
        image_b64: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> ClientResponse:
        """
        Extract text from an image using OpenAI Vision API format.

        Args:
            image_b64: Base64-encoded image string (without data URI prefix)
            prompt: Text prompt for the OCR task
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ClientResponse with extracted text
        """
        # Use OpenAI Vision API format for messages
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                            "detail": "high"
                        }
                    }
                ]
            }
        ]

        # Prepare kwargs for API call
        kwargs = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature

        # Make the API call using the OpenAI client
        client = self._get_client()
        response = client.chat.completions.create(**kwargs)

        # Convert to ClientResponse manually (standard OpenAI format)
        from datapizza.type import TextBlock
        from datapizza.core.clients.models import TokenUsage

        text_content = response.choices[0].message.content or ""

        return ClientResponse(
            content=[TextBlock(content=text_content)],
            stop_reason=response.choices[0].finish_reason,
            usage=TokenUsage(
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
                cached_tokens=response.usage.prompt_tokens_details.cached_tokens
                if response.usage.prompt_tokens_details
                else 0,
            ),
        )

    async def a_call_ocr(
        self,
        image_b64: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> ClientResponse:
        """
        Async version: Extract text from an image using OpenAI Vision API format.

        Args:
            image_b64: Base64-encoded image string (without data URI prefix)
            prompt: Text prompt for the OCR task
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ClientResponse with extracted text
        """
        # Use OpenAI Vision API format for messages
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                            "detail": "high"
                        }
                    }
                ]
            }
        ]

        # Prepare kwargs for API call
        kwargs = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature

        # Make the async API call using the OpenAI async client
        a_client = self._get_a_client()
        response = await a_client.chat.completions.create(**kwargs)

        # Convert to ClientResponse manually (standard OpenAI format)
        from datapizza.type import TextBlock
        from datapizza.core.clients.models import TokenUsage

        text_content = response.choices[0].message.content or ""

        return ClientResponse(
            content=[TextBlock(content=text_content)],
            stop_reason=response.choices[0].finish_reason,
            usage=TokenUsage(
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
                cached_tokens=response.usage.prompt_tokens_details.cached_tokens
                if response.usage.prompt_tokens_details
                else 0,
            ),
        )
