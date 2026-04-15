"""
Pydantic models / schemas for the Second Brain API.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    IMAGE = "image"
    MARKDOWN = "markdown"
    TEXT = "text"
    WEB = "web"


class ProcessingStage(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    SUMMARIZING = "summarizing"
    WRITING = "writing"
    DONE = "done"
    ERROR = "error"


class NoteType(str, Enum):
    SOURCE = "source"
    ARTICLE = "article"
    BOOK = "book"
    PAPER = "paper"
    WEB = "web"
    IMAGE = "image"


class UploadResponse(BaseModel):
    id: str
    filename: str
    source_type: SourceType
    status: ProcessingStage = ProcessingStage.QUEUED
    message: str = "File uploaded successfully"


class URLRequest(BaseModel):
    url: str


class ProcessingStatus(BaseModel):
    id: str
    filename: str
    stage: ProcessingStage
    progress: int = Field(ge=0, le=100)
    message: str = ""


class NoteResult(BaseModel):
    id: str
    title: str
    summary: str
    keywords: List[str]
    source_type: SourceType
    source_name: str
    vault_path: str
    related_notes: List[str] = []
    created_at: datetime = Field(default_factory=datetime.now)


class HistoryItem(BaseModel):
    id: str
    filename: str
    title: str
    source_type: SourceType
    status: ProcessingStage
    keywords: List[str] = []
    summary: str = ""
    vault_path: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    error_message: str = ""


class ExtractionResult(BaseModel):
    text: str
    title: str = ""
    metadata: dict = {}


class SummaryResult(BaseModel):
    title: str
    summary: str
    keywords: List[str]
    key_points: List[str]
    note_type: NoteType = NoteType.SOURCE
    related_topics: List[str] = []
