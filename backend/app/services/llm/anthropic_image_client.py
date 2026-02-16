"""
Anthropic Image Client - Anthropic/Claude client with vision/OCR capabilities

This client extends AnthropicClient with proper OCR support using Claude's Vision API format.
"""
from typing import Optional
from datapizza.core.cache import Cache
from datapizza.core.clients import ClientResponse
from datapizza.clients.anthropic import AnthropicClient

from .base_image_client import BaseImageClient


class AnthropicImageClient(BaseImageClient, AnthropicClient):
    """
    Anthropic/Claude client with vision support.

    Extends AnthropicClient with proper call_ocr() implementations that send
    images using Claude's Vision API format.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
        system_prompt: str = "",
        temperature: float | None = None,
        cache: Cache | None = None,
    ):
        # Call parent class constructor
        AnthropicClient.__init__(
            self,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            cache=cache,
        )

    def call_ocr(
        self,
        image_b64: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> ClientResponse:
        """
        Extract text from an image using Claude Vision API format.

        Args:
            image_b64: Base64-encoded image string (without data URI prefix)
            prompt: Text prompt for the OCR task
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ClientResponse with extracted text
        """
        # Use Claude Vision API format for messages
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
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
        if self.system_prompt:
            kwargs["system"] = self.system_prompt

        # Make the API call using the Anthropic client
        client = self._get_client()
        response = client.messages.create(**kwargs)

        # Convert to ClientResponse
        return self._response_to_client_response(response, tool_map=None)

    async def a_call_ocr(
        self,
        image_b64: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> ClientResponse:
        """
        Async version: Extract text from an image using Claude Vision API format.

        Args:
            image_b64: Base64-encoded image string (without data URI prefix)
            prompt: Text prompt for the OCR task
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ClientResponse with extracted text
        """
        # Use Claude Vision API format for messages
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
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
        if self.system_prompt:
            kwargs["system"] = self.system_prompt

        # Make the async API call using the Anthropic async client
        a_client = self._get_a_client()
        response = await a_client.messages.create(**kwargs)

        # Convert to ClientResponse
        return self._response_to_client_response(response, tool_map=None)
