"""
BaseImageClient - Extension of datapizza Client with OCR capabilities

This class extends the base Client with OCR-specific methods for vision tasks.
Subclasses can override these methods to provide provider-specific implementations.
"""
from typing import Optional
from datapizza.core.clients import Client, ClientResponse
from datapizza.core.cache import Cache


class BaseImageClient(Client):
    """
    Extended Client with OCR/vision capabilities.

    Adds call_ocr() methods for extracting text from images using vision models.
    Default implementation uses standard invoke(), but subclasses can override
    to use provider-specific vision APIs.
    """

    def call_ocr(
        self,
        image_b64: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> ClientResponse:
        """
        Extract text from an image using the vision model.

        Default implementation uses standard invoke(). Subclasses should override
        to use provider-specific vision APIs (e.g., Ollama's native images parameter).

        Args:
            image_b64: Base64-encoded image string
            prompt: Text prompt for the OCR task
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ClientResponse with extracted text
        """
        # Default implementation - uses standard invoke
        # Providers that don't support vision will fail here
        return self.invoke(
            input=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def a_call_ocr(
        self,
        image_b64: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> ClientResponse:
        """
        Async version of call_ocr().

        Extract text from an image using the vision model asynchronously.

        Args:
            image_b64: Base64-encoded image string
            prompt: Text prompt for the OCR task
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ClientResponse with extracted text
        """
        # Default implementation - uses standard a_invoke
        return await self.a_invoke(
            input=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
