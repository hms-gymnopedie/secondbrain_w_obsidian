"""
Upload and processing router.
Handles file uploads, URL scraping, and processing history.
"""
import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
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
    TagAnalysisResponse,
    TagGroup,
    TagMergeRequest,
    FolderCleanupRequest,
)
from backend.services.extractor import detect_source_type, extract_content, extract_from_url
from backend.services.summarizer import (
    summarize_content, 
    analyze_document_deep, 
    should_deep_analyze,
    group_tags_with_ai
)
from backend.services.obsidian_writer import (
    write_note, 
    write_deep_notes, 
    delete_folder_contents, 
    merge_tags_in_vault
)

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
        if conn in active_connections:
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
        if websocket in active_connections:
            active_connections.remove(websocket)


@router.post("/upload", response_model=List[UploadResponse])
async def upload_files(
    files: List[UploadFile] = File(...),
    folder: Optional[str] = Form(None)
):
    """Upload one or more files for processing."""
    print(f"📥 UPLOAD RECEIVED: folder={folder}, num_files={len(files)}")
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
        asyncio.create_task(
            _process_file(file_id, str(file_path), file.filename or "", source_type, folder)
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
    asyncio.create_task(_process_url(file_id, request.url, request.folder))

    return response


@router.get("/tags/analyze", response_model=TagAnalysisResponse)
async def analyze_tags():
    """Extract all tags from vault and find synonyms via AI."""
    vault_root = Path(settings.vault_path).resolve()
    import re
    tag_pattern = re.compile(r'(?<!#)\B#([a-zA-Z0-9_\-\u3131-\u318E\uAC00-\uD7A3]+)\b')
    all_tags = set()

    for path in vault_root.rglob("*.md"):
        if ".obsidian" in path.parts: continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_tags.update(tag_pattern.findall(f.read()))
        except: pass

    if not all_tags:
        return TagAnalysisResponse(suggested_groups=[])

    groups_data = await group_tags_with_ai(list(all_tags))

    suggested_groups = [
        TagGroup(
            primary_tag=g["primary_tag"],
            synonyms=g["synonyms"],
            reason=g["reason"]
        ) for g in groups_data
    ]

    return TagAnalysisResponse(suggested_groups=suggested_groups)


@router.post("/tags/merge")
async def merge_tags(request: TagMergeRequest):
    """Merge specified tags into a target tag."""
    result = merge_tags_in_vault(request.target_tag, request.tags_to_merge)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@router.post("/folders/cleanup")
async def cleanup_folder(request: FolderCleanupRequest):
    """Format a folder by deleting its contents."""
    result = delete_folder_contents(request.folder)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/folders/{folder_name}/info")
async def get_folder_info(folder_name: str):
    """Get information about a specific folder's contents."""
    vault_root = Path(settings.vault_path).resolve()
    target_dir = vault_root / folder_name

    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="폴더를 찾을 수 없습니다.")

    file_count = 0
    subfolder_count = 0
    total_size = 0

    for item in target_dir.rglob("*"):
        if item.is_file():
            file_count += 1
            total_size += item.stat().st_size
        elif item.is_dir() and item != target_dir:
            subfolder_count += 1

    # Convert size to readable format
    if total_size < 1024:
        size_str = f"{total_size} B"
    elif total_size < 1024 * 1024:
        size_str = f"{total_size / 1024:.1f} KB"
    else:
        size_str = f"{total_size / (1024 * 1024):.1f} MB"

    return {
        "folder": folder_name,
        "files": file_count,
        "subfolders": subfolder_count,
        "size": size_str
    }

@router.get("/folders", response_model=List[str])
async def get_folders():
    """Get list of user-created top-level category folders."""
    vault_root = Path(settings.vault_path).resolve()
    if not vault_root.exists():
        return []

    # Ignore system and default structural folders
    ignored = {"00_Inbox", "01_Sources", "02_MOC", "03_Concepts", "templates"}
    folders = []
    
    for d in vault_root.iterdir():
        if d.is_dir() and not d.name.startswith('.') and d.name not in ignored:
            folders.append(d.name)
            
    return sorted(folders)


@router.get("/stats")
async def get_stats():
    """Get real-time statistics from the Obsidian vault."""
    import time
    import re
    
    vault_root = Path(settings.vault_path).resolve()
    
    stats = {
        "notes": 0,
        "folders": 0,
        "tags": 0,
        "assets": 0,
        "storage": "0.0 MB",
        "today": 0
    }
    
    if not vault_root.exists():
        return stats
        
    now = time.time()
    one_day = 24 * 60 * 60
    unique_tags = set()
    total_size = 0
    
    # Pattern designed to match Obsidian tags covering alphanumeric and Korean characters
    tag_pattern = re.compile(r'(?<!#)\B#([a-zA-Z0-9_\\-\\u3131-\\u318E\\uAC00-\\uD7A3]+)\\b')
    
    for path in vault_root.rglob("*"):
        if ".obsidian" in path.parts:
            continue
            
        if path.is_file():
            try:
                stat = path.stat()
                total_size += stat.st_size
                
                if path.suffix == ".md":
                    stats["notes"] += 1
                    
                    # Check if modified today
                    if now - stat.st_mtime <= one_day:
                        stats["today"] += 1
                        
                    # Extract tags
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            text = f.read()
                            tags = tag_pattern.findall(text)
                            unique_tags.update(tags)
                    except Exception:
                        pass
                else:
                    if not path.name.startswith("."):
                        stats["assets"] += 1
            except Exception:
                pass
                    
        elif path.is_dir():
            if not path.name.startswith("."):
                stats["folders"] += 1

    stats["tags"] = len(unique_tags)
    
    # calculate smart size string
    if total_size < 1024 * 1024:
        stats["storage"] = f"{total_size / 1024:.1f} KB"
    else:
        stats["storage"] = f"{total_size / (1024 * 1024):.1f} MB"
    
    return stats


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


@router.delete("/note/{note_id}")
async def delete_note(note_id: str):
    """Delete a note and clean up all backlinks and MOC references."""
    from backend.services.obsidian_writer import delete_note_from_vault

    # Find the history item
    item = None
    for h in processing_history:
        if h.id == note_id:
            item = h
            break

    if not item:
        raise HTTPException(status_code=404, detail="노트를 찾을 수 없습니다.")

    # Delete from vault (file + backlinks + MOC)
    print(f"🗑️ DELETE 요청: id={note_id}, title={item.title}, vault_path={item.vault_path}, status={item.status}")
    if item.vault_path and item.status == ProcessingStage.DONE:
        try:
            delete_note_from_vault(
                vault_path=item.vault_path,
                note_title=item.title,
                keywords=item.keywords,
                folder=item.folder,
            )
        except Exception as e:
            print(f"❌ 삭제 오류: {e}")
            raise HTTPException(status_code=500, detail=f"노트 삭제 실패: {str(e)}")
    else:
        print(f"⚠️ 삭제 건너뜀: vault_path={item.vault_path}, status={item.status}")

    # Remove from history
    if item in processing_history:
        processing_history.remove(item)

    # Broadcast deletion
    import json
    msg = json.dumps({"type": "deleted", "id": note_id})
    disconnected = []
    for conn in active_connections:
        try:
            await conn.send_text(msg)
        except Exception:
            disconnected.append(conn)
    for conn in disconnected:
        if conn in active_connections:
            active_connections.remove(conn)

    return {"message": "노트가 삭제되었습니다.", "id": note_id}


async def _process_file(
    file_id: str,
    file_path: str,
    original_filename: str,
    source_type: SourceType,
    folder: Optional[str] = None,
):
    """Process an uploaded file through the full pipeline."""
    history_item = HistoryItem(
        id=file_id,
        filename=original_filename,
        title="처리 중...",
        source_type=source_type,
        status=ProcessingStage.EXTRACTING,
        folder=folder or "",
    )
    processing_history.append(history_item)

    try:
        # Stage 1: Extract content (0-30%)
        await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.EXTRACTING, progress=10, message="파일 읽는 중..."))
        await asyncio.sleep(0.8)

        extraction = await extract_content(file_path, source_type)

        await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.EXTRACTING, progress=30, message="텍스트 변환 완료"))
        await asyncio.sleep(0.8)

        if not extraction.text.strip():
            history_item.status = ProcessingStage.ERROR
            history_item.error_message = "텍스트를 추출할 수 없습니다."
            await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.ERROR, progress=0, message="텍스트 추출 실패"))
            return

        # Stage 2: Analyze with AI (30-80%)
        use_deep = should_deep_analyze(extraction.text)

        if use_deep:
            await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.SUMMARIZING, progress=45, message="🔬 AI 심층 분석 중..."))
            await asyncio.sleep(1.0)

            analysis = await analyze_document_deep(text=extraction.text, title=extraction.title, source=original_filename)

            await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.SUMMARIZING, progress=75, message="지식 구조화 완료"))
            await asyncio.sleep(1.0)

            # Stage 3: Write hierarchical notes
            await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.WRITING, progress=85, message="Obsidian 노트 생성 중..."))
            await asyncio.sleep(0.8)

            vault_path = await write_deep_notes(analysis=analysis, source_type=source_type, source_name=original_filename, folder=folder)

            history_item.title = analysis.title
            history_item.summary = analysis.overall_summary
            history_item.keywords = analysis.keywords
            history_item.vault_path = vault_path
            history_item.status = ProcessingStage.DONE

            await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.DONE, progress=100, message="✅ 완료!"))

        else:
            await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.SUMMARIZING, progress=50, message="AI 요약 중..."))
            await asyncio.sleep(1.0)

            summary = await summarize_content(text=extraction.text, title=extraction.title, source=original_filename)

            await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.SUMMARIZING, progress=75, message="요약 완료"))
            await asyncio.sleep(1.0)

            # Stage 3: Write to Obsidian vault
            await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.WRITING, progress=90, message="노트 기록 중..."))
            await asyncio.sleep(0.8)

            vault_path = await write_note(summary_result=summary, source_type=source_type, source_name=original_filename, folder=folder)

            history_item.title = summary.title
            history_item.summary = summary.summary
            history_item.keywords = summary.keywords
            history_item.vault_path = vault_path
            history_item.status = ProcessingStage.DONE

            await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.DONE, progress=100, message="✅ 완료!"))

    except Exception as e:
        history_item.status = ProcessingStage.ERROR
        history_item.error_message = str(e)
        await broadcast_status(ProcessingStatus(id=file_id, filename=original_filename, stage=ProcessingStage.ERROR, progress=0, message=f"오류: {str(e)}"))

    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass


async def _process_url(file_id: str, url: str, folder: Optional[str] = None):
    """Process a URL through the full pipeline."""
    history_item = HistoryItem(
        id=file_id,
        filename=url,
        title="처리 중...",
        source_type=SourceType.WEB,
        status=ProcessingStage.EXTRACTING,
        folder=folder or "",
    )
    processing_history.append(history_item)

    try:
        # Stage 1: Extract (0-30%)
        await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.EXTRACTING, progress=10, message="URL 연결 시도 중..."))
        await asyncio.sleep(0.8)

        await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.EXTRACTING, progress=25, message="웹페이지 스크래핑 중..."))
        extraction = await extract_from_url(url)
        await asyncio.sleep(0.8)

        if not extraction.text.strip():
            history_item.status = ProcessingStage.ERROR
            history_item.error_message = "내용을 가져올 수 없습니다."
            await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.ERROR, progress=0, message="스크래핑 실패"))
            return

        # Stage 2: Analyze (30-80%)
        use_deep = should_deep_analyze(extraction.text)

        if use_deep:
            await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.SUMMARIZING, progress=45, message="🔬 심층 분석 중..."))
            await asyncio.sleep(1.0)

            analysis = await analyze_document_deep(text=extraction.text, title=extraction.title, source=url)

            await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.SUMMARIZING, progress=70, message="지식 구조화 완료"))
            await asyncio.sleep(1.0)

            await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.WRITING, progress=85, message="연관 노트 생성 중..."))
            await asyncio.sleep(0.8)

            vault_path = await write_deep_notes(analysis=analysis, source_type=SourceType.WEB, source_name=extraction.title or url, source_url=url, folder=folder)

            history_item.title = analysis.title
            history_item.summary = analysis.overall_summary
            history_item.keywords = analysis.keywords
            history_item.vault_path = vault_path
            history_item.status = ProcessingStage.DONE

            await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.DONE, progress=100, message="✅ 완료!"))

        else:
            await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.SUMMARIZING, progress=50, message="AI 요약 진행 중..."))
            await asyncio.sleep(1.0)

            summary = await summarize_content(text=extraction.text, title=extraction.title, source=url)

            await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.SUMMARIZING, progress=75, message="요약 완료"))
            await asyncio.sleep(1.0)

            await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.WRITING, progress=90, message="Obsidian 기록 중..."))
            await asyncio.sleep(0.8)

            vault_path = await write_note(summary_result=summary, source_type=SourceType.WEB, source_name=extraction.title or url, source_url=url, folder=folder)

            history_item.title = summary.title
            history_item.summary = summary.summary
            history_item.keywords = summary.keywords
            history_item.vault_path = vault_path
            history_item.status = ProcessingStage.DONE

            await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.DONE, progress=100, message="✅ 완료!"))

    except Exception as e:
        history_item.status = ProcessingStage.ERROR
        history_item.error_message = str(e)
        await broadcast_status(ProcessingStatus(id=file_id, filename=url, stage=ProcessingStage.ERROR, progress=0, message=f"오류: {str(e)}"))
