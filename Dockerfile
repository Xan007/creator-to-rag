FROM python:3.12-slim AS base

# Install system dependencies (ffmpeg for video/audio processing, curl for healthchecks)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable package management
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency specifications first for layer caching
COPY pyproject.toml uv.lock README.md ./

# Sync production dependencies with api extras
RUN uv sync --no-dev --extra api

# Copy application source code
COPY src ./src
COPY config ./config
COPY storage ./storage
COPY main.py ./

# Create non-root user and persistent directories
RUN useradd -m -u 1000 crag \
    && mkdir -p /data/config /data/raw /data/saved \
    && chown -R crag:crag /app /data

USER crag

# Default environment variables for cloud portability
ENV PYTHONUNBUFFERED=1 \
    CRAG_DATA_DIR=/data \
    CRAG_CONFIG_DIR=/data/config \
    CRAG_HOST=0.0.0.0 \
    CRAG_PORT=8000

VOLUME ["/data"]
EXPOSE 8000

# Healthcheck for container orchestration (Render, Fly.io, ECS, K8s, Cloud Run)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD ["uv", "run", "python", "-m", "src.api.main"]
