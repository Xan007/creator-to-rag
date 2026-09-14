"""Entrypoint for the CreatorRAG HTTP API."""
import os

import uvicorn

from config.env import getenv


def main():
    from storage.db import init_db
    init_db()

    host = getenv("HOST", "0.0.0.0")
    # Support both standard cloud PORT (Render, Railway, Fly.io, Cloud Run) and CRAG_PORT
    port_str = os.getenv("PORT") or getenv("PORT", "8000")
    port = int(port_str)

    uvicorn.run("src.api.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
