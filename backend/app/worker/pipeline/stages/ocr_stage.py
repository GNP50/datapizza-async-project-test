"""
Stage A: OCR & Text Extraction

Extract text from documents (PDF with OCR, or direct text extraction for textual files).
Implements the BaseStage pattern for modular pipeline execution.
"""

import logging
from uuid import UUID
from typing import Optional
from pathlib import Path

from sqlalchemy import select

from app.worker.pipeline.base import BaseStage, StageContext, StageConfig
from app.services.database import db_manager
from app.models.document import Document, DocumentProcessingState
from app.models.message import ProcessingState
from app.services.storage import storage_manager
from app.services.ocr import ocr_service
from app.services.processing_cache_service import processing_cache_service
from app.worker.utils.errors import ProcessingError


logger = logging.getLogger(__name__)


# MIME types che sono sicuramente testuali
TEXTUAL_MIME_TYPES = {
    'text/plain',
    'text/markdown',
    'text/html',
    'text/css',
    'text/javascript',
    'text/csv',
    'text/xml',
    'application/json',
    'application/javascript',
    'application/xml',
    'application/x-yaml',
    'application/yaml',
}

# MIME types che richiedono OCR
OCR_MIME_TYPES = {
    'application/pdf',
    'image/png',
    'image/jpeg',
    'image/jpg',
    'image/tiff',
    'image/bmp',
    'image/gif',
    'image/webp',
}

# Estensioni per i casi in cui il MIME type non sia affidabile
TEXTUAL_EXTENSIONS = {
    '.txt', '.md', '.markdown', '.rst',
    '.java', '.py', '.js', '.jsx', '.ts', '.tsx',
    '.c', '.cpp', '.cc', '.h', '.hpp',
    '.cs', '.rb', '.go', '.rs', '.swift', '.kt',
    '.php', '.html', '.htm', '.css', '.scss', '.sass',
    '.json', '.xml', '.yaml', '.yml', '.toml',
    '.csv', '.tsv', '.sql', '.sh', '.bash',
    '.r', '.scala', '.clj', '.ex', '.exs',
    '.vue', '.svelte', '.astro',
}


def is_textual_content(mime_type: Optional[str], filename: Optional[str]) -> bool:
    """
    Determina se un file è testuale basandosi su MIME type ed estensione.
    """
    # Check MIME type prima
    if mime_type:
        # Controlla MIME types espliciti
        if mime_type in TEXTUAL_MIME_TYPES:
            return True
        # Qualsiasi cosa che inizia con text/
        if mime_type.startswith('text/'):
            return True

    # Fallback su estensione file
    if filename:
        file_ext = Path(filename).suffix.lower()
        if file_ext in TEXTUAL_EXTENSIONS:
            return True

    return False


def decode_text_content(content: bytes, filename: Optional[str] = None) -> str:
    """
    Decodifica il contenuto binario in testo usando rilevamento automatico dell'encoding.
    """
    import chardet

    # Prova prima con UTF-8 (più comune)
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        pass

    # Usa chardet per rilevare l'encoding
    detection = chardet.detect(content)
    detected_encoding = detection.get('encoding')
    confidence = detection.get('confidence', 0)

    logger.info(f"Detected encoding: {detected_encoding} (confidence: {confidence:.2%})")

    if detected_encoding and confidence > 0.5:
        try:
            return content.decode(detected_encoding)
        except (UnicodeDecodeError, LookupError) as e:
            logger.warning(f"Failed to decode with detected encoding {detected_encoding}: {e}")

    # Fallback: prova encodings comuni
    common_encodings = ['latin-1', 'cp1252', 'iso-8859-1', 'utf-16', 'ascii']

    for encoding in common_encodings:
        try:
            text = content.decode(encoding)
            logger.info(f"Successfully decoded with fallback encoding: {encoding}")
            return text
        except (UnicodeDecodeError, LookupError):
            continue

    # Ultima risorsa: decodifica con errori ignorati
    logger.warning(f"Using UTF-8 with error handling for file: {filename}")
    return content.decode('utf-8', errors='replace')


class OCRStage(BaseStage[None, dict]):
    """
    Stage A: OCR & Text Extraction

    Extracts text from documents using either:
    - Direct text extraction for textual files (.txt, .md, code files, etc.)
    - OCR service for PDF and image files

    Uses content-hash based caching to avoid re-processing identical files.

    Configuration:
        - cache_enabled: Enable/disable caching (default: True)
        - custom_params.ocr_confidence_threshold: Minimum OCR confidence (default: 0.6)
    """

    def __init__(self, config: StageConfig):
        super().__init__(config)

    async def execute(self, ctx: StageContext, input_data: None) -> dict:
        """
        Extract text from document.

        Args:
            ctx: Stage context with document_id
            input_data: None (first stage)

        Returns:
            Dictionary with extracted text and metadata:
            {
                "text": str,
                "pages": list[dict],
                "page_count": int,
                "method": "ocr" | "direct_text_extraction",
                "confidence": float
            }
        """
        document_id = ctx.document_id

        async with db_manager.session() as db:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()

            if not document:
                raise ProcessingError(f"Document {document_id} not found")

            # Download document content
            content = await storage_manager.download(document.file_path)

            # Check cache first (if enabled)
            extracted_data = None
            if self.config.cache_enabled:
                content_hash = processing_cache_service.compute_content_hash(content)
                cache_stage = self.config.cache_stage_name or "ocr_extraction"

                cached_result = await processing_cache_service.get_cached_result(
                    content_hash=content_hash,
                    stage=cache_stage,
                    db=db
                )

                if cached_result:
                    self.logger.info(f"Cache HIT for document {document_id}")
                    extracted_data = cached_result
                    # Update document with cached content
                    await self._update_document(db, document, extracted_data)

            # Cache miss - perform extraction
            if not extracted_data:
                self.logger.info(f"Cache MISS for document {document_id}")
                content_hash = processing_cache_service.compute_content_hash(content)

                # Determine extraction method
                if is_textual_content(document.mime_type, document.filename):
                    extracted_data = await self._extract_text_file(document, content, db)
                else:
                    extracted_data = await self._extract_ocr(document, content, db)

                # Cache the result
                if self.config.cache_enabled:
                    cache_stage = self.config.cache_stage_name or "ocr_extraction"
                    await processing_cache_service.set_cached_result(
                        content_hash=content_hash,
                        stage=cache_stage,
                        result_data=extracted_data,
                        document_id=document_id,
                        metadata={
                            "method": extracted_data.get("method", "ocr"),
                            "mime_type": document.mime_type,
                            "filename": document.filename
                        },
                        db=db
                    )

            # Store extracted text and metadata in context
            ctx.set("extracted_text", extracted_data["text"])
            ctx.set("extraction_method", extracted_data.get("method", "unknown"))
            ctx.set("page_count", extracted_data.get("page_count", 1))

            return extracted_data

    async def _extract_text_file(
        self,
        document: Document,
        content: bytes,
        db
    ) -> dict:
        """Extract text from textual files without OCR."""
        self.logger.info(f"Extracting text directly from: {document.filename}")

        text = decode_text_content(content, document.filename)

        # Update document
        await self._update_document(db, document, {"text": text})

        # Store full extracted text
        md_path = document.file_path.replace(document.filename, f"{document.id}.md")
        await storage_manager.upload(md_path, text.encode("utf-8"))

        return {
            "text": text,
            "pages": [{
                "page_number": 1,
                "text": text,
                "confidence": 1.0
            }],
            "page_count": 1,
            "method": "direct_text_extraction"
        }

    async def _extract_ocr(
        self,
        document: Document,
        content: bytes,
        db
    ) -> dict:
        """Extract text using OCR service."""
        if document.mime_type not in OCR_MIME_TYPES:
            self.logger.warning(
                f"Unexpected MIME type for OCR: {document.mime_type} "
                f"(file: {document.filename})"
            )

        self.logger.info(f"Performing OCR on {document.filename} ({document.mime_type})")

        # Get OCR confidence threshold from config
        confidence_threshold = self.config.custom_params.get("ocr_confidence_threshold", 0.6)

        # Perform OCR
        ocr_result = await ocr_service.extract_text(content, document.mime_type)

        # Check confidence
        if ocr_result.confidence < confidence_threshold:
            self.logger.warning(
                f"Low OCR confidence: {ocr_result.confidence:.2f} < {confidence_threshold}"
            )

        # Update document
        await self._update_document(db, document, {"text": ocr_result.text})

        # Store full extracted text
        md_path = document.file_path.replace(document.filename, f"{document.id}.md")
        await storage_manager.upload(md_path, ocr_result.text.encode("utf-8"))

        return {
            "text": ocr_result.text,
            "pages": ocr_result.pages,
            "page_count": ocr_result.page_count,
            "method": ocr_result.method,
            "confidence": ocr_result.confidence
        }

    async def _update_document(self, db, document: Document, extraction_data: dict) -> None:
        """Update document with extraction results."""
        text = extraction_data.get("text", "")
        document.extracted_content = text[:500]  # Preview
        document.processed = True
        await db.commit()

    @classmethod
    def from_settings(cls, settings) -> 'OCRStage':
        """Create OCRStage from application settings."""
        config = StageConfig.from_settings(
            settings,
            stage_name="ocr_extraction",
            document_state=DocumentProcessingState.OCR_EXTRACTION,
            message_state=ProcessingState.OCR_EXTRACTION,
            cache_enabled=True,
            custom_params={
                "ocr_confidence_threshold": 0.6
            }
        )
        return cls(config)
