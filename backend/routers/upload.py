"""
Upload and processing router.
Handles file uploads, URL scraping, and processing history.
"""
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
import aiofiles

from backend.config import settings
from backend.models.schemas import (
    UploadResponse,
    URLRequest,
    ProcessingStatus,
    ProcessingStage,
    NoteResult,
    HistoryItem,
    SourceType,
)
from backend.services.extractor import detect_source_type, extract_content, extract_from_url
from backend.services.summarizer import summarize_content
from backend.services.obsidian_writer import write_note

router = APIRouter(prefix="/api", tags=["upload"])

# In-memory history store (replace with DB for production)
processing_history: List[HistoryItem] = []

# WebSocket connections for real-time updates
active_connections: List[WebSocket] = []


ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
    ".md", ".txt", ".csv",
}


async def broadcast_status(status: ProcessingStatus):
    """Broadcast processing status to all connected WebSocket clients."""
    import json
    message = json.dumps(status.model_dump(), default=str)
    disconnected = []
    for conn in active_connections:
        try:
            await conn.send_text(message)
        except Exception:
            disconnected.append(conn)
    for conn in disconnected:
        active_connections.remove(conn)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time processing status."""
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)


@router.post("/upload", response_model=List[UploadResponse])
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload one or more files for processing."""
    responses = []

    for file in files:
        # Validate file extension
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            responses.append(
                UploadResponse(
                    id=str(uuid.uuid4()),
                    filename=file.filename or "unknown",
                    source_type=SourceType.TEXT,
                    status=ProcessingStage.ERROR,
                    message=f"지원하지 않는 파일 형식입니다: {ext}",
                )
            )
            continue

        # Validate file size
        content = await file.read()
        if len(content) > settings.max_file_size_bytes:
            responses.append(
                UploadResponse(
                    id=str(uuid.uuid4()),
                    filename=file.filename or "unknown",
                    source_type=SourceType.TEXT,
                    status=ProcessingStage.ERROR,
                    message=f"파일 크기가 {settings.max_file_size_mb}MB를 초과합니다.",
                )
            )
            continue

        # Save file
        file_id = str(uuid.uuid4())
        upload_dir = settings.upload_abs_path
        upload_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{file_id}{ext}"
        file_path = upload_dir / safe_name

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        source_type = detect_source_type(file.filename or "")

        response = UploadResponse(
            id=file_id,
            filename=file.filename or "unknown",
            source_type=source_type,
            status=ProcessingStage.QUEUED,
            message="파일이 업로드되었습니다. 처리를 시작합니다.",
        )
        responses.append(response)

        # Process the file asynchronously
        import asyncio
        asyncio.create_task(
            _process_file(file_id, str(file_path), file.filename or "", source_type)
        )

    return responses


@router.post("/url", response_model=UploadResponse)
async def process_url(request: URLRequest):
    """Process a web URL."""
    file_id = str(uuid.uuid4())

    response = UploadResponse(
        id=file_id,
        filename=request.url,
        source_type=SourceType.WEB,
        status=ProcessingStage.QUEUED,
        message="URL 처리를 시작합니다.",
    )

    # Process URL asynchronously
    import asyncio
    asyncio.create_task(_process_url(file_id, request.url))

    return response


@router.get("/history", response_model=List[HistoryItem])
async def get_history():
    """Get processing history."""
    return sorted(processing_history, key=lambda x: x.created_at, reverse=True)


@router.get("/note/{note_id}", response_model=HistoryItem)
async def get_note(note_id: str):
    """Get a specific note by ID."""
    for item in processing_history:
        if item.id == note_id:
            return item
    raise HTTPException(status_code=404, detail="노트를 찾을 수 없습니다.")


async def _process_file(
    file_id: str,
    file_path: str,
    original_filename: str,
    source_type: SourceType,
):
    """Process an uploaded file through the full pipeline."""
    history_item = HistoryItem(
        id=file_id,
        filename=original_filename,
        title="처리 중...",
        source_type=source_type,
        status=ProcessingStage.EXTRACTING,
    )
    processing_history.append(history_item)

    try:
        # Stage 1: Extract content
        await broadcast_status(
            ProcessingStatus(
                id=file_id,
                filename=original_filename,
                stage=ProcessingStage.EXTRACTING,
                progress=20,
                message="텍스트를 추출하고 있습니다...",
            )
        )

        extraction = await extract_content(file_path, source_type)

        if not extraction.text.strip():
            history_item.status = ProcessingStage.ERROR
            history_item.error_message = "텍스트를 추출할 수 없습니다."
            await broadcast_status(
                ProcessingStatus(
                    id=file_id,
                    filename=original_filename,
                    stage=ProcessingStage.ERROR,
                    progress=0,
                    message="텍스트 추출 실패",
                )
            )
            return

        # Stage 2: Summarize with AI
        await broadcast_status(
            ProcessingStatus(
                id=file_id,
                filename=original_filename,
                stage=ProcessingStage.SUMMARIZING,
                progress=50,
                message="AI가 내용을 분석하고 있습니다...",
            )
        )

        summary = await summarize_content(
            text=extraction.text,
            title=extraction.title,
            source=original_filename,
        )

        # Stage 3: Write to Obsidian vault
        await broadcast_status(
            ProcessingStatus(
                id=file_id,
                filename=original_filename,
                stage=ProcessingStage.WRITING,
                progress=80,
                message="Obsidian 노트를 생성하고 있습니다...",
            )
        )

        vault_path = await write_note(
            summary_result=summary,
            source_type=source_type,
            source_name=original_filename,
        )

        # Done
        history_item.title = summary.title
        history_item.summary = summary.summary
        history_item.keywords = summary.keywords
        history_item.vault_path = vault_path
        history_item.status = ProcessingStage.DONE

        await broadcast_status(
            ProcessingStatus(
                id=file_id,
                filename=original_filename,
                stage=ProcessingStage.DONE,
                progress=100,
                message=f"완료! 노트가 생성되었습니다: {vault_path}",
            )
        )

    except Exception as e:
        history_item.status = ProcessingStage.ERROR
        history_item.error_message = str(e)

        await broadcast_status(
            ProcessingStatus(
                id=file_id,
                filename=original_filename,
                stage=ProcessingStage.ERROR,
                progress=0,
                message=f"처리 중 오류 발생: {str(e)}",
            )
        )

    finally:
        # Clean up uploaded file
        try:
            os.remove(file_path)
        except Exception:
            pass


async def _process_url(file_id: str, url: str):
    """Process a URL through the full pipeline."""
    history_item = HistoryItem(
        id=file_id,
        filename=url,
        title="처리 중...",
        source_type=SourceType.WEB,
        status=ProcessingStage.EXTRACTING,
    )
    processing_history.append(history_item)

    try:
        # Stage 1: Extract from URL
        await broadcast_status(
            ProcessingStatus(
                id=file_id,
                filename=url,
                stage=ProcessingStage.EXTRACTING,
                progress=20,
                message="웹페이지를 스크래핑하고 있습니다...",
            )
        )

        extraction = await extract_from_url(url)

        if not extraction.text.strip():
            history_item.status = ProcessingStage.ERROR
            history_item.error_message = "웹페이지에서 텍스트를 추출할 수 없습니다."
            await broadcast_status(
                ProcessingStatus(
                    id=file_id,
                    filename=url,
                    stage=ProcessingStage.ERROR,
                    progress=0,
                    message="웹페이지 스크래핑 실패",
                )
            )
            return

        # Stage 2: Summarize
        await broadcast_status(
            ProcessingStatus(
                id=file_id,
                filename=url,
                stage=ProcessingStage.SUMMARIZING,
                progress=50,
                message="AI가 내용을 분석하고 있습니다...",
            )
        )

        summary = await summarize_content(
            text=extraction.text,
            title=extraction.title,
            source=url,
        )

        # Stage 3: Write to vault
        await broadcast_status(
            ProcessingStatus(
                id=file_id,
                filename=url,
                stage=ProcessingStage.WRITING,
                progress=80,
                message="Obsidian 노트를 생성하고 있습니다...",
            )
        )

        vault_path = await write_note(
            summary_result=summary,
            source_type=SourceType.WEB,
            source_name=extraction.title or url,
            source_url=url,
        )

        # Done
        history_item.title = summary.title
        history_item.summary = summary.summary
        history_item.keywords = summary.keywords
        history_item.vault_path = vault_path
        history_item.status = ProcessingStage.DONE

        await broadcast_status(
            ProcessingStatus(
                id=file_id,
                filename=url,
                stage=ProcessingStage.DONE,
                progress=100,
                message=f"완료! 노트가 생성되었습니다: {vault_path}",
            )
        )

    except Exception as e:
        history_item.status = ProcessingStage.ERROR
        history_item.error_message = str(e)

        await broadcast_status(
            ProcessingStatus(
                id=file_id,
                filename=url,
                stage=ProcessingStage.ERROR,
                progress=0,
                message=f"처리 중 오류 발생: {str(e)}",
            )
        )
