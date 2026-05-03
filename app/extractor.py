"""Content Registry - Pix2Text extraction service."""

import uuid
from pathlib import Path

from PIL import Image
from pix2text import Pix2Text

from app.config import UPLOADS_DIR

# Directory to save extracted image assets (diagrams, figures) permanently
ASSETS_DIR = UPLOADS_DIR / "extracted_assets"
ASSETS_DIR.mkdir(exist_ok=True)

# Lazy-load the model (downloads on first use, ~1-2 min)
_p2t_instance: Pix2Text | None = None

# Max image dimension — downscale larger images for speed
MAX_IMAGE_DIM = 1500


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
            return result.to_markdown(str(out_dir))
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


def extract_from_file(filepath: str, mode: str = "fast") -> str:
    """Extract text/markdown from an image or PDF file using Pix2Text.

    Args:
        filepath: Path to the file.
        mode: "fast" (skips layout detection, 3-5x faster) or
              "full" (full page analysis, slower but more accurate).

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

    p2t = _get_p2t()

    if ext in EXTRACTABLE_PDF_EXTS:
        result = p2t.recognize_pdf(str(path))
        return _result_to_text(result)

    # For images — optionally downscale
    process_path = _downscale_image(str(path))

    try:
        if mode == "fast":
            # Fast mode: recognize() — no layout detection, much faster
            result = p2t.recognize(process_path)
            return _result_to_text(result)
        else:
            # Full mode: recognize_page() — full layout analysis
            result = p2t.recognize_page(process_path)
            return _result_to_text(result)
    finally:
        # Clean up resized temp file
        if process_path != str(path) and Path(process_path).exists():
            Path(process_path).unlink()
