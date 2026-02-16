"""
Google Image Client - Google/Gemini client with vision/OCR capabilities

This client extends GoogleClient with proper OCR support using Gemini's Vision API format.
"""
from typing import Optional
from datapizza.core.cache import Cache
from datapizza.core.clients import ClientResponse
from datapizza.clients.google import GoogleClient

from .base_image_client import BaseImageClient


class GoogleImageClient(BaseImageClient, GoogleClient):
    """
    Google/Gemini client with vision support.

    Extends GoogleClient with proper call_ocr() implementations that send
    images using Gemini's Vision API format.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        system_prompt: str = "",
        temperature: float | None = None,
        cache: Cache | None = None,
    ):
        # Call parent class constructor
        GoogleClient.__init__(
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
        Extract text from an image using Gemini Vision API format.

        Args:
            image_b64: Base64-encoded image string (without data URI prefix)
            prompt: Text prompt for the OCR task
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ClientResponse with extracted text
        """
        import google.generativeai as genai
        from PIL import Image
        import io
        import base64

        # Convert base64 to PIL Image for Gemini
        image_bytes = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(image_bytes))

        # Prepare the content for Gemini (text + image)
        content = [prompt, image]

        # Prepare generation config
        generation_config = {
            "max_output_tokens": max_tokens,
        }
        if temperature is not None:
            generation_config["temperature"] = temperature

        # Make the API call using the Google client
        client = self._get_client()
        response = client.generate_content(
            content,
            generation_config=generation_config
        )

        # Convert to ClientResponse
        # For Google, we need to manually create a ClientResponse
        from datapizza.type import TextBlock
        from datapizza.core.clients.models import TokenUsage

        return ClientResponse(
            content=[TextBlock(content=response.text)],
            stop_reason="stop",
            usage=TokenUsage(
                prompt_tokens=0,  # Google doesn't always provide token counts
                completion_tokens=0,
                cached_tokens=0,
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
        Async version: Extract text from an image using Gemini Vision API format.

        Args:
            image_b64: Base64-encoded image string (without data URI prefix)
            prompt: Text prompt for the OCR task
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ClientResponse with extracted text
        """
        import google.generativeai as genai
        from PIL import Image
        import io
        import base64

        # Convert base64 to PIL Image for Gemini
        image_bytes = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(image_bytes))

        # Prepare the content for Gemini (text + image)
        content = [prompt, image]

        # Prepare generation config
        generation_config = {
            "max_output_tokens": max_tokens,
        }
        if temperature is not None:
            generation_config["temperature"] = temperature

        # Make the async API call using the Google async client
        a_client = self._get_a_client()
        response = await a_client.generate_content_async(
            content,
            generation_config=generation_config
        )

        # Convert to ClientResponse
        from datapizza.type import TextBlock
        from datapizza.core.clients.models import TokenUsage

        return ClientResponse(
            content=[TextBlock(content=response.text)],
            stop_reason="stop",
            usage=TokenUsage(
                prompt_tokens=0,  # Google doesn't always provide token counts
                completion_tokens=0,
                cached_tokens=0,
            ),
        )
