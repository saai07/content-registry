"""Content Registry - App Configuration."""

import os
from pathlib import Path


# Base directory (project root)
BASE_DIR = Path(__file__).resolve().parent.parent

# Upload directory
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

# Database
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_PATH = DATA_DIR / "content_registry.db"

# Upload limits
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    # Documents
    ".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    # Videos
    ".mp4", ".mkv", ".avi", ".mov", ".webm",
    # Audio
    ".mp3", ".wav", ".ogg",
}

# Predefined metadata options
CLASSES = [
    "Class 1", "Class 2", "Class 3", "Class 4", "Class 5",
    "Class 6", "Class 7", "Class 8", "Class 9", "Class 10",
    "Class 11", "Class 12",
]

SUBJECTS = [
    "Mathematics",
    "Science",
    "Physics",
    "Chemistry",
    "Biology",
    "English",
    "Hindi",
    "Social Science",
    "History",
    "Geography",
    "Political Science",
    "Economics",
    "Computer Science",
    "Accountancy",
    "Business Studies",
]

# Chapters are dynamic — stored in DB as users upload content.
# This dict provides starter suggestions per (class, subject).
DEFAULT_CHAPTERS: dict[str, dict[str, list[str]]] = {
    "Class 10": {
        "Mathematics": [
            "Chapter 1: Real Numbers",
            "Chapter 2: Polynomials",
            "Chapter 3: Pair of Linear Equations",
            "Chapter 4: Quadratic Equations",
            "Chapter 5: Arithmetic Progressions",
            "Chapter 6: Triangles",
            "Chapter 7: Coordinate Geometry",
            "Chapter 8: Trigonometry",
            "Chapter 9: Applications of Trigonometry",
            "Chapter 10: Circles",
            "Chapter 11: Areas Related to Circles",
            "Chapter 12: Surface Areas and Volumes",
            "Chapter 13: Statistics",
            "Chapter 14: Probability",
        ],
        "Science": [
            "Chapter 1: Chemical Reactions",
            "Chapter 2: Acids, Bases and Salts",
            "Chapter 3: Metals and Non-metals",
            "Chapter 4: Carbon and its Compounds",
            "Chapter 5: Life Processes",
            "Chapter 6: Control and Coordination",
            "Chapter 7: How do Organisms Reproduce",
            "Chapter 8: Heredity",
            "Chapter 9: Light",
            "Chapter 10: Human Eye",
            "Chapter 11: Electricity",
            "Chapter 12: Magnetic Effects",
            "Chapter 13: Our Environment",
        ],
    },
}
