"""
OCR Service - Abstraction layer for text extraction from documents.
Supports multiple backends: PyPDF2, Tesseract, AWS Textract, LLM-based OCR (via datapizza), etc.
"""
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass
import io
import PyPDF2
import base64
from pdf2image import convert_from_bytes
from PIL import Image
from datapizza.core.clients import Client


@dataclass
class OCRResult:
    """Result from OCR processing"""
    text: str
    page_count: int
    pages: list[dict[str, any]]  # List of {page_number, text, confidence}
    confidence: Optional[float] = None
    method: str = "unknown"


class OCRBackend(ABC):
    """Abstract base class for OCR backends"""

    @abstractmethod
    async def extract_text(self, content: bytes, mime_type: str) -> OCRResult:
        """Extract text from document content"""
        pass


class PyPDF2Backend(OCRBackend):
    """PyPDF2-based text extraction (no actual OCR, just PDF text extraction)"""

    async def extract_text(self, content: bytes, mime_type: str) -> OCRResult:
        if mime_type != "application/pdf":
            raise ValueError(f"PyPDF2Backend only supports PDF files, got {mime_type}")

        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
        pages = []
        full_text = ""

        for page_num, page in enumerate(pdf_reader.pages, start=1):
            page_text = page.extract_text()
            pages.append({
                "page_number": page_num,
                "text": page_text,
                "confidence": 1.0  # PDF text extraction is always 100% confident
            })
            full_text += page_text + "\n"

        return OCRResult(
            text=full_text.strip(),
            page_count=len(pages),
            pages=pages,
            confidence=1.0,
            method="pypdf2"
        )


class LLMOCRBackend(OCRBackend):
    """LLM-based OCR backend using vision models via datapizza Client"""

    def __init__(self, client: Client):
        """
        Initialize LLM OCR backend with a datapizza client.

        Args:
            client: Datapizza client instance (OpenAI, Anthropic, etc.) with vision support
        """
        self.client = client

    def _convert_pdf_to_images(self, content: bytes) -> list[Image.Image]:
        """Convert PDF bytes to list of PIL Images"""
        return convert_from_bytes(content, dpi=200)

    def _image_to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to base64 string"""
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    async def _extract_text_from_image(self, image_b64: str, page_num: int) -> dict:
        """Extract text from a single image using LLM vision model"""
        import asyncio

        # Prompt for OCR task
        prompt = "Extract all text from this document image. Return only the extracted text, preserving layout and formatting as much as possible."

        try:
            # Try to use specialized OCR methods in priority order:
            # 1. a_call_ocr() - async method (preferred)
            # 2. call_ocr() - sync method (run in thread pool)
            # 3. invoke() - fallback for backward compatibility

            if hasattr(self.client, "a_call_ocr"):
                # Preferred: use async OCR method
                response = await self.client.a_call_ocr(
                    image_b64=image_b64,
                    prompt=prompt,
                    temperature=0.0,
                    max_tokens=4096,
                )
            elif hasattr(self.client, "call_ocr"):
                # Second choice: use sync OCR method in thread pool
                def _sync_ocr():
                    return self.client.call_ocr(
                        image_b64=image_b64,
                        prompt=prompt,
                        temperature=0.0,
                        max_tokens=4096,
                    )
                response = await asyncio.to_thread(_sync_ocr)
            else:
                # Fallback: use standard invoke (for backward compatibility)
                # This may not work for all providers
                def _sync_invoke():
                    return self.client.invoke(input=prompt)
                response = await asyncio.to_thread(_sync_invoke)

            # Extract text from response
            text = (
                getattr(response, "text", None) or 
                getattr(response, "first_text", None) or 
                str(response.content[0].content if hasattr(response, "content") else "")
            )

            return {
                "page_number": page_num,
                "text": text,
                "confidence": 0.9  # LLM-based OCR confidence (estimated)
            }
        except Exception as e:
            raise RuntimeError(f"OCR extraction failed for page {page_num}: {str(e)}") from e

    async def extract_text(self, content: bytes, mime_type: str) -> OCRResult:
        """Extract text from document using LLM vision model"""
        if mime_type not in ["application/pdf", "image/png", "image/jpeg", "image/jpg"]:
            raise ValueError(f"LLMOCRBackend supports PDF and images, got {mime_type}")

        from app.core.config import get_settings
        settings = get_settings()

        ocr_parallel = getattr(settings, "ocr_parallel", False)
        max_concurrency = getattr(settings, "ocr_max_concurrency", 3)
        max_retries = getattr(settings, "ocr_max_retries", 3)

        pages = []
        full_text = ""

        if mime_type == "application/pdf":
            # Convert PDF to images
            images = self._convert_pdf_to_images(content)

            if ocr_parallel and len(images) > 1:
                # Process pages in parallel with concurrency limit
                import asyncio
                from asyncio import Semaphore

                semaphore = Semaphore(max_concurrency)

                async def process_page_with_retry(idx: int, image: Image.Image) -> dict:
                    """Process a single page with retry logic"""
                    async with semaphore:
                        image_b64 = self._image_to_base64(image)

                        for attempt in range(max_retries):
                            try:
                                return await self._extract_text_from_image(image_b64, idx)
                            except Exception as e:
                                if attempt < max_retries - 1:
                                    import logging
                                    logger = logging.getLogger(__name__)
                                    logger.warning(f"OCR retry {attempt + 1}/{max_retries} for page {idx}: {e}")
                                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                                else:
                                    raise

                # Process all pages in parallel
                tasks = [
                    process_page_with_retry(idx, image)
                    for idx, image in enumerate(images, start=1)
                ]
                pages = await asyncio.gather(*tasks)

                # Concatenate text from all pages
                full_text = "\n".join(page["text"] for page in pages)
            else:
                # Process each page sequentially
                for idx, image in enumerate(images, start=1):
                    image_b64 = self._image_to_base64(image)
                    page_result = await self._extract_text_from_image(image_b64, idx)
                    pages.append(page_result)
                    full_text += page_result["text"] + "\n"
        else:
            # Single image
            image = Image.open(io.BytesIO(content))
            image_b64 = self._image_to_base64(image)
            page_result = await self._extract_text_from_image(image_b64, 1)
            pages.append(page_result)
            full_text = page_result["text"]

        return OCRResult(
            text=full_text.strip(),
            page_count=len(pages),
            pages=pages,
            confidence=0.9,
            method=f"llm-ocr-{self.client.model_name}"
        )


class OCRService:
    """
    Main OCR service that manages different OCR backends.
    Provides a unified interface for text extraction from documents.
    """

    def __init__(self, backend: Optional[OCRBackend] = None):
        if backend:
            self.backend = backend
        else:
            self.backend = PyPDF2Backend()

    async def extract_text(self, content: bytes, mime_type: str) -> OCRResult:
        """
        Extract text from document content.

        Args:
            content: Raw document bytes
            mime_type: MIME type of the document

        Returns:
            OCRResult with extracted text and metadata
        """
        try:
            return await self.backend.extract_text(content, mime_type)
        except Exception as e:
            raise RuntimeError(f"OCR extraction failed: {str(e)}") from e

    def set_backend(self, backend: OCRBackend):
        """Switch to a different OCR backend"""
        self.backend = backend


def get_ocr_client() -> Client:
    """
    Factory function to get the appropriate datapizza client for OCR based on configuration.

    Returns a datapizza Client configured for vision/OCR tasks.
    Supported providers: openai, anthropic, google, ollama, openai_like
    """
    from app.core.config import get_settings

    settings = get_settings()
    ocr_llm_provider = getattr(settings, "ocr_llm_provider", "openai").lower()
    system_prompt = "You are an OCR assistant. Extract all text from document images accurately, preserving layout and formatting."

    if ocr_llm_provider == "openai":
        from app.services.llm.openai_image_client import OpenAIImageClient

        api_key = getattr(settings, "ocr_openai_api_key", None) or getattr(settings, "openai_api_key", None)
        if not api_key:
            raise ValueError("OCR_OPENAI_API_KEY or OPENAI_API_KEY is required for OCR with OpenAI")

        model = getattr(settings, "ocr_model", "gpt-4o-mini")  # gpt-4o-mini supports vision
        return OpenAIImageClient(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt
        )

    elif ocr_llm_provider == "anthropic":
        from app.services.llm.anthropic_image_client import AnthropicImageClient

        api_key = getattr(settings, "ocr_anthropic_api_key", None) or getattr(settings, "anthropic_api_key", None)
        if not api_key:
            raise ValueError("OCR_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY is required for OCR with Anthropic")

        model = getattr(settings, "ocr_model", "claude-3-haiku-20240307")  # Claude 3 supports vision
        return AnthropicImageClient(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt
        )

    elif ocr_llm_provider == "google":
        from app.services.llm.google_image_client import GoogleImageClient

        api_key = getattr(settings, "ocr_google_api_key", None) or getattr(settings, "google_api_key", None)
        if not api_key:
            raise ValueError("OCR_GOOGLE_API_KEY or GOOGLE_API_KEY is required for OCR with Google")

        model = getattr(settings, "ocr_model", "gemini-1.5-flash")  # Gemini supports vision
        return GoogleImageClient(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt
        )

    elif ocr_llm_provider == "ollama":
        from app.services.llm.ollama_datapizza_client import OllamaDatapizzaClient

        api_key = getattr(settings, "ocr_ollama_api_key", None) or settings.ollama_api_key
        if not api_key:
            raise ValueError("OCR_OLLAMA_API_KEY or OLLAMA_API_KEY is required for OCR with Ollama")

        base_url = getattr(settings, "ocr_ollama_base_url", None) or settings.ollama_base_url
        model = getattr(settings, "ocr_model", "ministral-3:14b-cloud")

        return OllamaDatapizzaClient(
            api_key=api_key,
            model=model,
            base_url=base_url,
            system_prompt=system_prompt
        )

    elif ocr_llm_provider == "openai_like":
        from app.services.llm.openai_like_image_client import OpenAILikeImageClient

        base_url = getattr(settings, "ocr_base_url", None)
        api_key = getattr(settings, "ocr_api_key", None)
        model = getattr(settings, "ocr_model", "vision-model")

        if not base_url or not api_key:
            raise ValueError("OCR_BASE_URL and OCR_API_KEY are required for openai_like provider")

        return OpenAILikeImageClient(
            api_key=api_key,
            model=model,
            base_url=base_url,
            system_prompt=system_prompt
        )

    else:
        raise ValueError(
            f"Unsupported OCR LLM provider: {ocr_llm_provider}. "
            f"Supported providers: openai, anthropic, google, ollama, openai_like"
        )


def get_ocr_service() -> OCRService:
    """
    Factory function to get the appropriate OCR service based on configuration.

    Returns OCRService with the correct backend based on OCR_PROVIDER setting:
    - llm: LLMOCRBackend (uses vision models via datapizza clients)
    - pypdf2: PyPDF2Backend (text extraction from PDFs)
    """
    from app.core.config import get_settings

    settings = get_settings()
    ocr_provider = getattr(settings, "ocr_provider", "pypdf2").lower()

    if ocr_provider == "llm":
        # Use LLM-based OCR with vision models via datapizza client
        client = get_ocr_client()
        backend = LLMOCRBackend(client=client)
        return OCRService(backend=backend)

    elif ocr_provider == "pypdf2":
        return OCRService(backend=PyPDF2Backend())

    else:
        raise ValueError(
            f"Unsupported OCR provider: {ocr_provider}. "
            f"Supported providers: llm, pypdf2"
        )


# Global instance - initialized with config-based backend
ocr_service = get_ocr_service()
