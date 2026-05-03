"""Content Registry - Content router (upload, list, get, delete, download)."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

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


@router.post("/upload", response_model=UploadResponse)
async def upload_content(
    file: UploadFile = File(..., description="The file to upload"),
    class_name: str = Form(..., description="Class (e.g., 'Class 10')"),
    subject: str = Form(..., description="Subject (e.g., 'Mathematics')"),
    chapter: str = Form(..., description="Chapter (e.g., 'Chapter 1: Real Numbers')"),
    description: str = Form("", description="Optional description or notes"),
    tags: str = Form("[]", description="JSON array of tags, e.g. '[\"important\", \"revision\"]'"),
):
    """Upload a content file with classification metadata."""

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

    return UploadResponse(content=ContentResponse(**record))


@router.post("/extract/quick", response_model=ExtractionResponse)
async def quick_extract(
    file: UploadFile = File(..., description="Image or PDF to extract text from"),
):
    """Quick extraction — upload a file and get extracted text without storing.

    Useful for testing pix2text or one-off extractions.
    The file is temporarily saved, processed, then deleted.
    """
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed.",
        )

    # Save temporarily
    temp_id = str(uuid.uuid4())
    temp_path = UPLOADS_DIR / f"_temp_{temp_id}{ext}"

    try:
        file_bytes = await file.read()
        with open(temp_path, "wb") as f:
            f.write(file_bytes)

        if not can_extract(str(temp_path)):
            raise HTTPException(
                status_code=400,
                detail=f"File type '{ext}' not supported for text extraction.",
            )

        extracted = extract_from_file(str(temp_path))

        return ExtractionResponse(
            id=temp_id,
            filename=file.filename,
            extracted_text=extracted,
            message="Quick extraction complete (file not stored)",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}",
        )
    finally:
        # Always clean up temp file
        if temp_path.exists():
            os.remove(temp_path)


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
    """Background task: run extraction and save to DB."""
    try:
        extracted = extract_from_file(filepath, mode=mode)
        update_extracted_text(content_id, extracted)
        print(f"Background extraction done for {content_id}")
    except Exception as e:
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

