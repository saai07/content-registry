"""Content Registry - Content router (upload, list, get, delete, download)."""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from app.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, UPLOADS_DIR
from app.database import (
    delete_content_by_id,
    get_all_content,
    get_content_by_id,
    insert_content,
    update_extracted_text,
)
from app.extractor import can_extract, extract_from_file
from app.models import (
    ContentListResponse,
    ContentResponse,
    DeleteResponse,
    ExtractionResponse,
    RenderResponse,
    UploadResponse,
)

router = APIRouter(prefix="/api/content", tags=["Content"])

# ---------------------------------------------------------------------------
# Extraction progress tracking (in-memory, single-worker safe)
# ---------------------------------------------------------------------------
_progress_lock = threading.Lock()
_progress: dict[str, dict] = {}


def _update_progress(content_id: str, percent: int, message: str):
    """Thread-safe update of extraction progress."""
    status = "completed" if percent >= 100 else ("failed" if percent < 0 else "processing")
    with _progress_lock:
        _progress[content_id] = {
            "percent": max(percent, 0),
            "message": message,
            "status": status,
        }


@router.post("/upload", response_model=UploadResponse)
async def upload_content(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The file to upload"),
    class_name: str = Form(..., description="Class (e.g., 'Class 10')"),
    subject: str = Form(..., description="Subject (e.g., 'Mathematics')"),
    chapter: str = Form(..., description="Chapter (e.g., 'Chapter 1: Real Numbers')"),
    description: str = Form("", description="Optional description or notes"),
    tags: str = Form("[]", description="JSON array of tags, e.g. '[\"important\", \"revision\"]'"),
):
    """Upload a content file with classification metadata.

    Extraction (full mode) is automatically triggered in the background
    for supported file types (images, PDFs). Poll GET /api/content/{id}
    to check when extracted_text is populated.
    """

    # Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    # Read file content
    file_bytes = await file.read()
    filesize = len(file_bytes)

    # Validate file size
    if filesize > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({filesize} bytes). Max: {MAX_FILE_SIZE} bytes ({MAX_FILE_SIZE // (1024*1024)}MB)",
        )

    if filesize == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Validate tags JSON
    try:
        parsed_tags = json.loads(tags)
        if not isinstance(parsed_tags, list):
            raise ValueError
        tags = json.dumps(parsed_tags)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Tags must be a valid JSON array, e.g. '[\"tag1\", \"tag2\"]'",
        )

    # Generate unique ID and save file
    content_id = str(uuid.uuid4())
    safe_filename = f"{content_id}{ext}"
    filepath = UPLOADS_DIR / safe_filename

    with open(filepath, "wb") as f:
        f.write(file_bytes)

    # Store metadata in database
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": content_id,
        "filename": file.filename,
        "filepath": str(filepath),
        "mimetype": file.content_type or "application/octet-stream",
        "filesize": filesize,
        "class_name": class_name.strip(),
        "subject": subject.strip(),
        "chapter": chapter.strip(),
        "description": description.strip(),
        "tags": tags,
        "created_at": now,
        "updated_at": now,
    }

    record = insert_content(data)

    # Auto-trigger full extraction in background for extractable files
    if can_extract(str(filepath)):
        background_tasks.add_task(
            _run_extraction_background, content_id, str(filepath), "full"
        )

    return UploadResponse(content=ContentResponse(**record))


@router.post("/upload-extract", tags=["Upload + Extract"])
async def upload_and_extract(
    file: UploadFile = File(..., description="The file to upload"),
    class_name: str = Form(..., description="Class (e.g., 'Class 10')"),
    subject: str = Form(..., description="Subject (e.g., 'Mathematics')"),
    chapter: str = Form(..., description="Chapter (e.g., 'Chapter 1: Real Numbers')"),
    description: str = Form("", description="Optional description or notes"),
    tags: str = Form("[]", description="JSON array of tags"),
):
    """Upload a file AND extract text in one call with live progress.

    Returns a **Server-Sent Events (SSE)** stream. Each event is JSON:

    ```
    data: {"percent": 42, "message": "Extracting page 3/7...", "status": "processing"}
    data: {"percent": 100, "message": "Done", "status": "completed", "content_id": "...", "extracted_text": "..."}
    ```

    The final event (percent=100) includes the full `extracted_text` and `content_id`.
    """
    import queue
    import threading

    # ── Validate ──────────────────────────────────────────────────
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed.")

    file_bytes = await file.read()
    filesize = len(file_bytes)

    if filesize > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max: {MAX_FILE_SIZE // (1024*1024)}MB")
    if filesize == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        parsed_tags = json.loads(tags)
        if not isinstance(parsed_tags, list):
            raise ValueError
        tags = json.dumps(parsed_tags)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Tags must be a valid JSON array")

    # ── Save file ─────────────────────────────────────────────────
    content_id = str(uuid.uuid4())
    safe_filename = f"{content_id}{ext}"
    filepath = UPLOADS_DIR / safe_filename

    with open(filepath, "wb") as f:
        f.write(file_bytes)

    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": content_id,
        "filename": file.filename,
        "filepath": str(filepath),
        "mimetype": file.content_type or "application/octet-stream",
        "filesize": filesize,
        "class_name": class_name.strip(),
        "subject": subject.strip(),
        "chapter": chapter.strip(),
        "description": description.strip(),
        "tags": tags,
        "created_at": now,
        "updated_at": now,
    }
    insert_content(data)

    # ── If not extractable, return immediately ────────────────────
    if not can_extract(str(filepath)):
        import json as _json

        async def _no_extract():
            yield f"data: {_json.dumps({'percent': 100, 'message': 'File saved (not extractable)', 'status': 'completed', 'content_id': content_id, 'extracted_text': ''})}\n\n"

        return StreamingResponse(_no_extract(), media_type="text/event-stream")

    # ── Stream extraction progress via SSE ────────────────────────
    progress_q: queue.Queue = queue.Queue()

    def _extract_thread():
        """Run extraction in a thread, push progress events to the queue."""
        import json as _json
        try:
            def on_progress(pct: int, msg: str):
                progress_q.put({"percent": pct, "message": msg, "status": "processing"})

            extracted = extract_from_file(str(filepath), mode="full", progress_cb=on_progress)
            update_extracted_text(content_id, extracted)
            progress_q.put({
                "percent": 100,
                "message": "Extraction complete",
                "status": "completed",
                "content_id": content_id,
                "extracted_text": extracted,
            })
        except Exception as e:
            progress_q.put({"percent": 0, "message": f"Failed: {str(e)}", "status": "failed"})

    thread = threading.Thread(target=_extract_thread, daemon=True)
    thread.start()

    async def _event_stream():
        import json as _json
        import asyncio
        while True:
            try:
                event = progress_q.get(timeout=0.5)
            except queue.Empty:
                # Send keep-alive comment so connection doesn't drop
                yield ": keepalive\n\n"
                continue

            yield f"data: {_json.dumps(event)}\n\n"

            if event.get("status") in ("completed", "failed"):
                break

    return StreamingResponse(_event_stream(), media_type="text/event-stream")





@router.get("", response_model=ContentListResponse)
async def list_content(
    class_name: str | None = None,
    subject: str | None = None,
    chapter: str | None = None,
    search: str | None = None,
):
    """List all content with optional filters.

    - **class_name**: Filter by class (e.g., 'Class 10')
    - **subject**: Filter by subject (e.g., 'Mathematics')
    - **chapter**: Filter by chapter
    - **search**: Search in filename, description, chapter
    """
    items = get_all_content(
        class_name=class_name,
        subject=subject,
        chapter=chapter,
        search=search,
    )
    return ContentListResponse(
        total=len(items),
        items=[ContentResponse(**item) for item in items],
    )


@router.get("/{content_id}", response_model=ContentResponse)
async def get_content(content_id: str):
    """Get details of a single content item by ID."""
    record = get_content_by_id(content_id)
    if not record:
        raise HTTPException(status_code=404, detail="Content not found")
    return ContentResponse(**record)


@router.get("/{content_id}/progress", tags=["Extraction"])
async def get_extraction_progress(content_id: str):
    """Get real-time extraction progress for a content item.

    Returns:
        - **percent**: 0–100 (integer)
        - **status**: "processing", "completed", or "failed"
        - **message**: Human-readable status, e.g. "Extracting page 3/7..."

    If extraction hasn't started or the ID is unknown, checks the DB:
    if extracted_text already exists, returns 100%.
    """
    with _progress_lock:
        progress = _progress.get(content_id)

    if progress:
        return progress

    # Fallback: check if extraction already finished (progress dict cleared or missed)
    record = get_content_by_id(content_id)
    if not record:
        raise HTTPException(status_code=404, detail="Content not found")

    if record.get("extracted_text"):
        return {"percent": 100, "message": "Extraction complete", "status": "completed"}

    return {"percent": 0, "message": "Extraction not started", "status": "pending"}


@router.get("/{content_id}/download")
async def download_content(content_id: str):
    """Download the file associated with a content item."""
    record = get_content_by_id(content_id)
    if not record:
        raise HTTPException(status_code=404, detail="Content not found")

    filepath = Path(record["filepath"])
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(filepath),
        filename=record["filename"],
        media_type=record["mimetype"],
    )


@router.delete("/{content_id}", response_model=DeleteResponse)
async def delete_content(content_id: str):
    """Delete a content item and its associated file."""
    record = get_content_by_id(content_id)
    if not record:
        raise HTTPException(status_code=404, detail="Content not found")

    # Delete file from disk
    filepath = Path(record["filepath"])
    if filepath.exists():
        os.remove(filepath)

    # Delete from database
    delete_content_by_id(content_id)

    return DeleteResponse(id=content_id)


def _run_extraction_background(content_id: str, filepath: str, mode: str):
    """Background task: run extraction and save to DB with progress tracking."""
    def on_progress(pct: int, msg: str):
        _update_progress(content_id, pct, msg)

    try:
        _update_progress(content_id, 0, "Starting extraction...")
        extracted = extract_from_file(filepath, mode=mode, progress_cb=on_progress)
        update_extracted_text(content_id, extracted)
        _update_progress(content_id, 100, "Extraction complete")
        print(f"Background extraction done for {content_id}")
    except Exception as e:
        _update_progress(content_id, -1, f"Failed: {str(e)}")
        print(f"Background extraction failed for {content_id}: {e}")


@router.post("/{content_id}/extract", response_model=ExtractionResponse)
async def extract_content_text(
    content_id: str,
    background_tasks: BackgroundTasks,
    mode: str = Query("fast", description="'fast' (skips layout, 3-5x faster) or 'full' (accurate but slow)"),
    background: bool = Query(False, description="Run in background? Returns immediately, check result later."),
):
    """Run pix2text OCR on an uploaded content item.

    - **mode=fast**: Skips layout detection, 3-5x faster. Good for simple images.
    - **mode=full**: Full page analysis. Slower but handles complex layouts.
    - **background=true**: Returns immediately, extraction runs in background.
      Check result later via GET /api/content/{id}.
    """
    record = get_content_by_id(content_id)
    if not record:
        raise HTTPException(status_code=404, detail="Content not found")

    filepath = record["filepath"]

    if not can_extract(filepath):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported for extraction. File: {record['filename']}",
        )

    if not Path(filepath).exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    if background:
        # Run in background — return immediately
        background_tasks.add_task(_run_extraction_background, content_id, filepath, mode)
        return ExtractionResponse(
            id=content_id,
            filename=record["filename"],
            extracted_text="",
            message=f"Extraction started in background (mode={mode}). Check GET /api/content/{content_id} for result.",
        )

    # Synchronous extraction
    try:
        extracted = extract_from_file(filepath, mode=mode)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}",
        )

    update_extracted_text(content_id, extracted)

    return ExtractionResponse(
        id=content_id,
        filename=record["filename"],
        extracted_text=extracted,
    )


@router.get("/{content_id}/render", response_class=HTMLResponse)
async def render_content(content_id: str):
    """Render extracted content as a beautiful HTML page.

    Open this URL in a browser to see text, math (LaTeX), and images
    rendered in correct reading order.
    """
    record = get_content_by_id(content_id)
    if not record:
        raise HTTPException(status_code=404, detail="Content not found")

    extracted = record.get("extracted_text", "")
    if not extracted:
        raise HTTPException(
            status_code=400,
            detail="No extracted text found. Run POST /api/content/{id}/extract first.",
        )

    # Convert absolute Windows paths to HTTP /uploads/... URLs
    uploads_abs = str(UPLOADS_DIR).replace("\\", "/")
    markdown = extracted.replace("\\", "/")
    markdown = markdown.replace(uploads_abs, "/uploads")

    # Escape backticks for JS template literal
    safe_md = markdown.replace("`", "\\`").replace("${", "\\${")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{record["filename"]} — Content Registry</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
MathJax = {{ tex: {{ inlineMath: [['$','$']], displayMath: [['$$','$$']] }}, startup: {{ typeset: false }} }};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',sans-serif;background:#0f1117;color:#e2e8f0;padding:0}}
header{{background:#1a1d2e;border-bottom:1px solid #2d3154;padding:20px 40px}}
header h1{{font-size:18px;font-weight:700;color:#c7d2fe}}
header p{{font-size:12px;color:#64748b;margin-top:4px}}
.badge{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;background:#1e3a5f;color:#60a5fa;margin-top:8px;margin-right:6px}}
main{{max-width:800px;margin:40px auto;padding:0 40px 80px;line-height:1.9}}
main h1,main h2,main h3{{color:#c7d2fe;margin:28px 0 12px;font-weight:600}}
main h1{{font-size:28px;border-bottom:1px solid #2d3154;padding-bottom:10px}}
main h2{{font-size:22px}}
main p{{color:#cbd5e1;margin:12px 0;font-size:15px}}
main img{{max-width:100%;border-radius:10px;margin:20px 0;border:1px solid #2d3154;display:block}}
main table{{width:100%;border-collapse:collapse;margin:16px 0}}
main th{{background:#1e293b;padding:10px 14px;color:#c7d2fe;text-align:left}}
main td{{padding:10px 14px;border-bottom:1px solid #1e293b;color:#cbd5e1}}
main code{{background:#1e293b;padding:2px 6px;border-radius:4px;font-size:13px;color:#a5f3fc}}
main pre{{background:#1e293b;padding:16px;border-radius:10px;overflow-x:auto;margin:16px 0}}
main blockquote{{border-left:3px solid #818cf8;padding-left:16px;color:#94a3b8;margin:16px 0}}
.back-link{{display:inline-block;margin:20px 0 0 40px;color:#818cf8;text-decoration:none;font-size:13px}}
.back-link:hover{{text-decoration:underline}}
</style>
</head>
<body>
<a class="back-link" href="/docs">← Back to API docs</a>
<header>
  <h1>{record["filename"]}</h1>
  <p>{record.get("description","")}</p>
  <span class="badge">{record["class_name"]}</span>
  <span class="badge">{record["subject"]}</span>
  <span class="badge">{record["chapter"]}</span>
</header>
<main id="content"></main>
<script>
const md = `{safe_md}`;
document.getElementById('content').innerHTML = marked.parse(md);
if (window.MathJax) MathJax.typesetPromise([document.getElementById('content')]);
</script>
</body>
</html>"""
    return HTMLResponse(content=html)

