"""Content Registry - FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import UPLOADS_DIR
from app.database import init_db
from app.routers import content, metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    print("Swagger docs → http://localhost:8000/docs")
    yield


app = FastAPI(
    title="Content Registry",
    description=(
        "A microservice for uploading and classifying educational content.\n\n"
        "Upload files, tag them by **Class**, **Subject**, and **Chapter**, "
        "and retrieve them with powerful filters.\n\n"
        "Designed to be agent-friendly for future knowledge graph integration."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(content.router)
app.include_router(metadata.router)

# Serve uploaded files + extracted assets as static files
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.get("/", tags=["Health"])
async def root():
    """Health check / root endpoint."""
    return {
        "service": "Content Registry",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }
