from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime
from uuid import UUID
from typing import Any
from enum import Enum


class ChatCreate(BaseModel):
    title: str | None = None


class ChatUpdate(BaseModel):
    title: str


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str | None
    summary: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str | None = None
    chat_id: UUID | None = None


class FactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID
    content: str
    page_number: int | None
    verification_status: str
    web_source_url: list[str]
    confidence_score: float
    verification_reasoning: str | None
    created_at: datetime

    @field_validator('web_source_url', mode='before')
    @classmethod
    def parse_web_source_url(cls, v):
        """Parse web_source_url from DB (newline-separated string) to list."""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            # Split by newline and filter empty strings
            return [url.strip() for url in v.split('\n') if url.strip()]
        return []


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID
    filename: str
    file_size: int
    mime_type: str
    processed: bool
    processing_state: str
    web_search_enabled: bool
    created_at: datetime
    facts: list[FactResponse] = []


class FactCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID
    claim: str
    verification_status: str
    confidence_score: float
    sources: dict
    created_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID
    chat_id: UUID
    role: str
    content: str
    processing_state: str
    created_at: datetime
    updated_at: datetime
    fact_checks: list[FactCheckResponse] = []
    documents: list[DocumentResponse] = []
    response_cached: bool | None = None
    response_type: str | None = None
    response_metadata: dict | None = None


class MessageStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID
    processing_state: str
    content: str
    fact_checks: list[FactCheckResponse]
