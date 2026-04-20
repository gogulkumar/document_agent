# ── Stage 1: build ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .

# Install system dependencies for weasyprint, PyMuPDF, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf2.0-0 \
    libffi-dev libssl-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy system libs required at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create runtime directories
RUN mkdir -p uploads exports snapshot inmemory_conversation

# Expose port
EXPOSE 5000

# Environment defaults (override via --env or .env file)
ENV FLASK_PORT=5000
ENV NOTEBOOK_AGENT_UPLOAD_DIR=/app/uploads
ENV NOTEBOOK_AGENT_EXPORT_DIR=/app/exports
ENV USE_BEDROCK=false

# Run with gunicorn (production) — timeout 600s for long LLM pipelines
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--timeout", "600", \
     "--chdir", "context_agent_UI/flask_app", \
     "app:app"]
