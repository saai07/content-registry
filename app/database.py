"""Content Registry - Database layer using SQLite."""

import sqlite3
from pathlib import Path

from app.config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Initialize the database schema."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS content (
                id          TEXT PRIMARY KEY,
                filename    TEXT NOT NULL,
                filepath    TEXT NOT NULL,
                mimetype    TEXT NOT NULL,
                filesize    INTEGER NOT NULL,
                class_name  TEXT NOT NULL,
                subject     TEXT NOT NULL,
                chapter     TEXT NOT NULL,
                description    TEXT DEFAULT '',
                tags           TEXT DEFAULT '[]',
                extracted_text TEXT DEFAULT '',
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_content_class
                ON content(class_name);
            CREATE INDEX IF NOT EXISTS idx_content_subject
                ON content(subject);
            CREATE INDEX IF NOT EXISTS idx_content_chapter
                ON content(chapter);
            CREATE INDEX IF NOT EXISTS idx_content_created
                ON content(created_at);
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def insert_content(data: dict) -> dict:
    """Insert a new content record and return it."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO content
                (id, filename, filepath, mimetype, filesize,
                 class_name, subject, chapter, description, tags,
                 created_at, updated_at)
            VALUES
                (:id, :filename, :filepath, :mimetype, :filesize,
                 :class_name, :subject, :chapter, :description, :tags,
                 :created_at, :updated_at)
            """,
            data,
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM content WHERE id = ?", (data["id"],)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_all_content(
    class_name: str | None = None,
    subject: str | None = None,
    chapter: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """List content with optional filters."""
    conn = get_connection()
    try:
        query = "SELECT * FROM content WHERE 1=1"
        params: list = []

        if class_name:
            query += " AND class_name = ?"
            params.append(class_name)
        if subject:
            query += " AND subject = ?"
            params.append(subject)
        if chapter:
            query += " AND chapter = ?"
            params.append(chapter)
        if search:
            query += " AND (filename LIKE ? OR description LIKE ? OR chapter LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like])

        query += " ORDER BY created_at DESC"

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_content_by_id(content_id: str) -> dict | None:
    """Get a single content record by ID."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM content WHERE id = ?", (content_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_content_by_id(content_id: str) -> bool:
    """Delete a content record. Returns True if a row was deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM content WHERE id = ?", (content_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def update_extracted_text(content_id: str, extracted_text: str) -> dict | None:
    """Update the extracted_text field for a content record."""
    from datetime import datetime, timezone

    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE content SET extracted_text = ?, updated_at = ? WHERE id = ?",
            (extracted_text, now, content_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM content WHERE id = ?", (content_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_distinct_values(column: str, filters: dict | None = None) -> list[str]:
    """Get distinct values for a column, with optional filters."""
    allowed_columns = {"class_name", "subject", "chapter"}
    if column not in allowed_columns:
        raise ValueError(f"Column must be one of {allowed_columns}")

    conn = get_connection()
    try:
        query = f"SELECT DISTINCT {column} FROM content WHERE 1=1"
        params: list = []

        if filters:
            for key, value in filters.items():
                if key in allowed_columns and value:
                    query += f" AND {key} = ?"
                    params.append(value)

        query += f" ORDER BY {column}"
        rows = conn.execute(query, params).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()
