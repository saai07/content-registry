"""Content Registry - Metadata router (classes, subjects, chapters)."""

from fastapi import APIRouter

from app.config import CLASSES, DEFAULT_CHAPTERS, SUBJECTS
from app.database import get_distinct_values
from app.models import MetadataResponse

router = APIRouter(prefix="/api/metadata", tags=["Metadata"])


@router.get("/classes", response_model=MetadataResponse)
async def list_classes():
    """Get all available class options.

    Returns predefined classes merged with any classes found in existing content.
    """
    db_classes = get_distinct_values("class_name")
    all_classes = sorted(set(CLASSES) | set(db_classes))
    return MetadataResponse(values=all_classes, total=len(all_classes))


@router.get("/subjects", response_model=MetadataResponse)
async def list_subjects(class_name: str | None = None):
    """Get all available subject options.

    Optionally filter by class to see which subjects have content for that class.

    - **class_name**: Optional class filter (e.g., 'Class 10')
    """
    db_subjects = get_distinct_values(
        "subject",
        filters={"class_name": class_name} if class_name else None,
    )

    if class_name:
        # Return DB subjects for this class, merged with predefined
        all_subjects = sorted(set(SUBJECTS) | set(db_subjects))
    else:
        all_subjects = sorted(set(SUBJECTS) | set(db_subjects))

    return MetadataResponse(values=all_subjects, total=len(all_subjects))


@router.get("/chapters", response_model=MetadataResponse)
async def list_chapters(
    class_name: str | None = None,
    subject: str | None = None,
):
    """Get available chapter options.

    Filters by class and/or subject. Returns chapters from existing content
    merged with any predefined defaults.

    - **class_name**: Filter by class (e.g., 'Class 10')
    - **subject**: Filter by subject (e.g., 'Mathematics')
    """
    filters = {}
    if class_name:
        filters["class_name"] = class_name
    if subject:
        filters["subject"] = subject

    db_chapters = get_distinct_values(
        "chapter",
        filters=filters if filters else None,
    )

    # Merge with predefined defaults if available
    default = []
    if class_name and subject:
        default = DEFAULT_CHAPTERS.get(class_name, {}).get(subject, [])

    all_chapters = sorted(set(default) | set(db_chapters))
    return MetadataResponse(values=all_chapters, total=len(all_chapters))
