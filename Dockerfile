FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    CRAG_HOST=0.0.0.0 CRAG_PORT=8000 CRAG_CONFIG_DIR=/app/state \
    CRAG_DATA_DIR=/app/data PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY config ./config
COPY storage ./storage
RUN useradd --uid 10001 --create-home crag && mkdir -p /app/state /app/data \
    && chown -R crag:crag /app
EXPOSE 8000

FROM base AS ingest
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-dev --extra api --extra ingest --no-editable
USER crag
CMD ["crag-api"]

FROM base AS query
RUN uv sync --frozen --no-dev --extra api --no-editable
USER crag
CMD ["crag-query-api"]
