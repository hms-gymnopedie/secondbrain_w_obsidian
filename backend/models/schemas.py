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
    folder: Optional[str] = None


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
    folder: str = ""
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


class SectionType(str, Enum):
    BACKGROUND = "background"
    INTRODUCTION = "introduction"
    METHODOLOGY = "methodology"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    LITERATURE_REVIEW = "literature_review"
    ANALYSIS = "analysis"
    OTHER = "other"


class SectionResult(BaseModel):
    """A logical section extracted from a large document."""
    section_type: SectionType = SectionType.OTHER
    title: str
    summary: str
    key_points: List[str] = []
    importance: str = "medium"  # high, medium, low
    evidence_type: str = ""  # empirical, theoretical, statistical, etc.
    claims: List[str] = []
    position: int = 0  # order within the document


class AtomicConcept(BaseModel):
    """An atomic knowledge unit extracted from the document."""
    name: str
    definition: str
    related_topics: List[str] = []
    importance: str = "medium"


class DeepAnalysisResult(BaseModel):
    """Result of deep hierarchical document analysis."""
    title: str
    overall_summary: str
    document_type: str = ""  # paper, report, article, etc.
    keywords: List[str] = []
    note_type: NoteType = NoteType.SOURCE
    sections: List[SectionResult] = []
    atomic_concepts: List[AtomicConcept] = []
    related_topics: List[str] = []

