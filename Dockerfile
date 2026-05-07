FROM python:3.11-slim

WORKDIR /app

# System deps required by pix2text (OpenCV, libGL, etc.)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces enforces uid 1000 — create matching user
RUN useradd -m -u 1000 -s /bin/bash appuser

# Pre-create data directories with correct ownership
RUN mkdir -p /app/data /app/uploads/extracted_assets \
    && chown -R appuser:appuser /app

# Install Python dependencies (cached layer — only rebuilds when requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir --use-deprecated=legacy-resolver -r requirements.txt

# Copy application source
COPY --chown=appuser:appuser app/ ./app/

USER appuser

# Runtime environment (override in HF Space → Settings → Variables)
ENV DATABASE_PATH=/app/data/content_registry.db \
    UPLOADS_DIR=/app/uploads \
    ALLOWED_ORIGINS=* \
    PORT=7860

# HF Spaces requires port 7860
EXPOSE 7860

# 1 gunicorn worker — pix2text model is ~700 MB; more workers = OOM
# timeout=300 gives pix2text time to finish a full-page extraction
CMD ["gunicorn", "app.main:app", \
     "-w", "1", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:7860", \
     "--timeout", "300", \
     "--keep-alive", "5", \
     "--access-logfile", "-"]
