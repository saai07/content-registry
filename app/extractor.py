"""Content Registry - Pix2Text extraction service with progress tracking."""

import base64
import io
import re
import uuid
from pathlib import Path
from typing import Callable, Optional

import fitz  # PyMuPDF — used for page-by-page PDF processing with progress
from PIL import Image
from pix2text import Pix2Text

from app.config import BASE_URL, UPLOADS_DIR

# Type alias for the progress callback: (percent: int, message: str) -> None
ProgressCallback = Optional[Callable[[int, str], None]]

# Directory to save extracted image assets (diagrams, figures) permanently
ASSETS_DIR = UPLOADS_DIR / "extracted_assets"
ASSETS_DIR.mkdir(exist_ok=True)

# Lazy-load the model (downloads on first use, ~1-2 min)
_p2t_instance: Pix2Text | None = None

# Max image dimension — downscale larger images for speed
MAX_IMAGE_DIM = 1500

# Regex to find markdown image references: ![alt](path)
_IMG_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# MIME types for base64 encoding
_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _embed_images_as_base64(markdown_text: str, base_dir: str | Path) -> str:
    """Replace image file references in markdown with base64 data URIs.

    Finds all ``![alt](path)`` patterns, reads the image file from disk,
    optionally resizes it (if > MAX_IMAGE_DIM), encodes it as a base64
    data URI, and replaces the path in-place.

    If an image file doesn't exist or can't be read, the original
    reference is left untouched (no crash).

    Args:
        markdown_text: Extracted markdown containing image references.
        base_dir: Directory that relative image paths are resolved against.

    Returns:
        Markdown with image paths replaced by ``data:image/...;base64,...`` URIs.
    """
    base_dir = Path(base_dir)

    def _replace_match(match: re.Match) -> str:
        alt_text = match.group(1)
        img_path_str = match.group(2)

        # Skip if already a URL or data URI
        if img_path_str.startswith(("http://", "https://", "data:")):
            return match.group(0)

        # Resolve relative path against base_dir
        img_path = Path(img_path_str)
        if not img_path.is_absolute():
            img_path = base_dir / img_path

        if not img_path.exists():
            print(f"  [base64] Image not found, skipping: {img_path}")
            return match.group(0)

        try:
            img = Image.open(img_path)

            # Resize if too large
            w, h = img.size
            if max(w, h) > MAX_IMAGE_DIM:
                ratio = MAX_IMAGE_DIM / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

            # Determine format and MIME type
            suffix = img_path.suffix.lower()
            mime = _MIME_MAP.get(suffix, "image/png")
            save_format = "JPEG" if "jpeg" in mime else suffix.lstrip(".").upper()
            if save_format == "JPG":
                save_format = "JPEG"

            # Encode to base64
            buffer = io.BytesIO()
            img.save(buffer, format=save_format)
            b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

            data_uri = f"data:{mime};base64,{b64}"
            print(f"  [base64] Embedded {img_path.name} ({w}x{h} → {img.size[0]}x{img.size[1]}, {len(b64)//1024}KB)")
            return f"![{alt_text}]({data_uri})"

        except Exception as e:
            print(f"  [base64] Failed to encode {img_path}: {e}")
            return match.group(0)

    return _IMG_PATTERN.sub(_replace_match, markdown_text)


def _rewrite_paths_to_urls(text: str) -> str:
    """Replace local filesystem paths in extracted markdown with public URLs.

    pix2text saves extracted figures to UPLOADS_DIR/extracted_assets/...
    Those paths are only valid on the server. This function rewrites them
    to full public URLs so external clients (e.g. AuraDocs RAG app) can
    load the images.

    Example:
        /app/uploads/extracted_assets/abc/fig.png
        → https://your-space.hf.space/uploads/extracted_assets/abc/fig.png
    """
    # Normalise to forward slashes (handles Windows dev paths too)
    local_prefix = str(UPLOADS_DIR).replace("\\", "/")
    normalised   = text.replace("\\", "/")
    return normalised.replace(local_prefix, f"{BASE_URL}/uploads")


def _get_p2t() -> Pix2Text:
    """Get or initialize the Pix2Text model (singleton)."""
    global _p2t_instance
    if _p2t_instance is None:
        print("Loading Pix2Text model...")
        _p2t_instance = Pix2Text.from_config()
        print("Pix2Text model loaded!")
    return _p2t_instance


# File types that pix2text can handle
EXTRACTABLE_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
EXTRACTABLE_PDF_EXTS = {".pdf"}
EXTRACTABLE_EXTS = EXTRACTABLE_IMAGE_EXTS | EXTRACTABLE_PDF_EXTS


def can_extract(filepath: str) -> bool:
    """Check if a file type is supported for text extraction."""
    ext = Path(filepath).suffix.lower()
    return ext in EXTRACTABLE_EXTS


def _downscale_image(filepath: str) -> str:
    """Downscale large images to speed up processing. Returns path to use."""
    try:
        img = Image.open(filepath)
        w, h = img.size

        # Only downscale if image is larger than MAX_IMAGE_DIM
        if max(w, h) <= MAX_IMAGE_DIM:
            return filepath

        # Calculate new size keeping aspect ratio
        ratio = MAX_IMAGE_DIM / max(w, h)
        new_w, new_h = int(w * ratio), int(h * ratio)

        img_resized = img.resize((new_w, new_h), Image.LANCZOS)

        # Save to temp file
        temp_path = filepath + "_resized.png"
        img_resized.save(temp_path)
        print(f"Downscaled {w}x{h} → {new_w}x{new_h} for faster processing")
        return temp_path
    except Exception:
        return filepath


def _result_to_text(result) -> str:
    """Convert a pix2text result (Page/Document) to a permanent markdown string.

    Extracted figures/images are saved permanently to ASSETS_DIR so they
    can be served and linked in the output markdown.
    """
    # Use a permanent, uniquely named folder so images are not deleted
    if hasattr(result, 'to_markdown'):
        try:
            out_dir = ASSETS_DIR / uuid.uuid4().hex
            out_dir.mkdir(parents=True, exist_ok=True)
            md = result.to_markdown(str(out_dir))
            # Embed images as base64 immediately while files are still on disk
            md = _embed_images_as_base64(md, out_dir)
            return md
        except Exception:
            pass

    # Fallback: try to_text
    if hasattr(result, 'to_text'):
        try:
            return result.to_text()
        except Exception:
            pass

    # Last fallback: str representation
    return str(result)


# ---------------------------------------------------------------------------
# PDF page-by-page extraction with real progress
# ---------------------------------------------------------------------------

def _extract_pdf_with_progress(
    filepath: Path,
    p2t: Pix2Text,
    progress_cb: ProgressCallback = None,
) -> str:
    """Extract text from a PDF page-by-page using PyMuPDF + pix2text.

    Reports real per-page progress via the callback.
    """
    doc = fitz.open(str(filepath))
    total_pages = len(doc)

    if progress_cb:
        progress_cb(5, f"PDF loaded — {total_pages} page(s) detected")

    page_results = []
    # Shared asset dir for all pages of this PDF
    assets_id = uuid.uuid4().hex
    page_assets_dir = ASSETS_DIR / assets_id
    page_assets_dir.mkdir(parents=True, exist_ok=True)

    for i in range(total_pages):
        page = doc[i]

        if progress_cb:
            pct = 10 + int((i / total_pages) * 80)  # 10% → 90%
            progress_cb(pct, f"Extracting page {i + 1}/{total_pages}...")

        # Render page to image at 200 DPI for good OCR quality
        pix = page.get_pixmap(dpi=200)
        page_img_path = page_assets_dir / f"_page_{i}.png"
        pix.save(str(page_img_path))

        # Process with pix2text full layout analysis
        result = p2t.recognize_page(str(page_img_path))
        page_text = _result_to_text(result)
        page_results.append(page_text)

        # Clean up the temporary page image (assets from recognize stay)
        page_img_path.unlink(missing_ok=True)

    doc.close()

    if progress_cb:
        progress_cb(92, "Combining pages...")

    combined = "\n\n---\n\n".join(page_results)

    if progress_cb:
        progress_cb(95, "Embedding images as base64...")

    # Base64 embedding is already done per-page in _result_to_text,
    # but run _rewrite_paths_to_urls as fallback for any missed paths
    return _rewrite_paths_to_urls(combined)


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------

def extract_from_file(
    filepath: str,
    mode: str = "full",
    progress_cb: ProgressCallback = None,
) -> str:
    """Extract text/markdown from an image or PDF file using Pix2Text.

    Args:
        filepath: Path to the file.
        mode: "fast" (skips layout detection, 3-5x faster) or
              "full" (full page analysis, slower but more accurate).
        progress_cb: Optional callback(percent: int, message: str) for
                     real-time progress reporting.

    Returns:
        Extracted content as Markdown string (includes LaTeX for math formulas).
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    ext = path.suffix.lower()
    if ext not in EXTRACTABLE_EXTS:
        raise ValueError(
            f"File type '{ext}' not supported for extraction. "
            f"Supported: {sorted(EXTRACTABLE_EXTS)}"
        )

    if progress_cb:
        progress_cb(2, "Loading pix2text model...")

    p2t = _get_p2t()

    # ── PDF: page-by-page with real progress ──────────────────────
    if ext in EXTRACTABLE_PDF_EXTS:
        return _extract_pdf_with_progress(path, p2t, progress_cb)

    # ── Image extraction ──────────────────────────────────────────
    if progress_cb:
        progress_cb(10, "Preparing image...")

    process_path = _downscale_image(str(path))

    try:
        if progress_cb:
            progress_cb(20, "Running OCR & formula recognition...")

        if mode == "fast":
            result = p2t.recognize(process_path)
        else:
            result = p2t.recognize_page(process_path)

        if progress_cb:
            progress_cb(85, "Saving results...")

        text = _result_to_text(result)

        if progress_cb:
            progress_cb(95, "Embedding images as base64...")

        # Base64 embedding is already done in _result_to_text,
        # _rewrite_paths_to_urls catches any remaining file paths as fallback
        return _rewrite_paths_to_urls(text)
    finally:
        # Clean up resized temp file
        if process_path != str(path) and Path(process_path).exists():
            Path(process_path).unlink()
