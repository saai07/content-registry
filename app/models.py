"""Content Registry - Pydantic models for request/response validation."""

from pydantic import BaseModel, Field


class ContentResponse(BaseModel):
    """Response model for a single content item."""

    id: str
    filename: str
    filepath: str
    mimetype: str
    filesize: int
    class_name: str
    subject: str
    chapter: str
    description: str = ""
    tags: str = "[]"
    extracted_text: str = ""
    created_at: str
    updated_at: str


class ContentListResponse(BaseModel):
    """Response model for content listing."""

    total: int
    items: list[ContentResponse]


class UploadResponse(BaseModel):
    """Response after a successful upload."""

    message: str = "Content uploaded successfully"
    content: ContentResponse


class DeleteResponse(BaseModel):
    """Response after deleting content."""

    message: str = "Content deleted successfully"
    id: str


class MetadataResponse(BaseModel):
    """Response for metadata endpoints (classes, subjects, chapters)."""

    values: list[str]
    total: int


class ExtractionResponse(BaseModel):
    """Response after running pix2text extraction on a content item."""

    id: str
    filename: str
    extracted_text: str
    message: str = "Text extracted successfully"


class RenderResponse(BaseModel):
    """Response for the render endpoint — markdown ready for display."""

    id: str
    filename: str
    class_name: str
    subject: str
    chapter: str
    markdown: str
    message: str = "Render ready"
