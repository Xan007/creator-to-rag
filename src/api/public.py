"""Internet-facing API. No ingestion, administration, cookies, or local media."""

import hashlib
import json
import logging
import secrets
import threading
import time
from collections import deque
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.env import getenv
from config.users import UserInfo, load_user_by_id
from src.api.schemas import PublicQuery
from src.api.limits import RequestBodyLimit

logger = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)
_query_slots = threading.BoundedSemaphore(4)
_rate_lock = threading.Lock()
_recent_queries: dict[str, deque[float]] = {}


def load_token_users() -> dict[str, str]:
    try:
        users = json.loads(getenv("PUBLIC_TOKEN_USERS", "{}"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("CRAG_PUBLIC_TOKEN_USERS must be a JSON object.") from exc
    if not isinstance(users, dict) or not users or any(
        not isinstance(digest, str) or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
        or not isinstance(user_id, str) or not user_id.strip()
        for digest, user_id in users.items()
    ):
        raise RuntimeError("Configure SHA-256 token digests mapped to existing user IDs.")
    return users


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_token_users()
    yield


app = FastAPI(title="CreatorRAG Query API", version="0.3.0", lifespan=lifespan)
app.add_middleware(RequestBodyLimit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in getenv("CORS_ORIGINS", "").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)


def authenticated_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> UserInfo:
    if credentials is None:
        raise HTTPException(401, "Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    user_id = next((uid for key, uid in load_token_users().items() if secrets.compare_digest(key, digest)), None)
    user = load_user_by_id(user_id) if user_id else None
    if user is None:
        raise HTTPException(401, "Invalid credentials.", headers={"WWW-Authenticate": "Bearer"})
    return user


def query_budget(user: UserInfo = Depends(authenticated_user)):
    now = time.monotonic()
    with _rate_lock:
        for identity in list(_recent_queries):
            if not _recent_queries[identity] or _recent_queries[identity][-1] <= now - 60:
                del _recent_queries[identity]
        recent = _recent_queries.setdefault(user.id, deque())
        while recent and recent[0] <= now - 60:
            recent.popleft()
        if len(recent) >= 20:
            raise HTTPException(429, "Too many queries. Please wait.", headers={"Retry-After": "60"})
        if not _query_slots.acquire(blocking=False):
            raise HTTPException(503, "Query capacity is busy. Please retry.", headers={"Retry-After": "5"})
        recent.append(now)
    try:
        yield user
    finally:
        _query_slots.release()


@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
def health():
    return {"status": "ok", "service": "query"}


@app.get("/libraries")
def libraries(user: UserInfo = Depends(authenticated_user)):
    from src.pipeline.library import list_libraries
    return list_libraries(user.id)


@app.post("/query")
def query(body: PublicQuery, user: UserInfo = Depends(query_budget)):
    from src.pipeline.library import resolve_library
    from src.pipeline.query import query_knowledge
    try:
        library_id = resolve_library(user.id, body.library)
    except ValueError:
        raise HTTPException(404, "Library not found.") from None
    try:
        return query_knowledge(
            body.question, library_id=library_id, user_id=user.id,
            mode=body.mode, top_k=body.top_k, min_score=body.min_score,
            history=[turn.model_dump() for turn in body.history], allow_hydration=False,
        )
    except Exception:
        logger.exception("Query failed")
        raise HTTPException(502, "Could not complete the query. Please retry.") from None


@app.get("/libraries/{library_id}/sources")
def sources(
    library_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    user: UserInfo = Depends(authenticated_user),
):
    from src.pipeline.library import resolve_library
    from storage.db import get_session
    from storage.models import Source
    try:
        resolved = resolve_library(user.id, library_id)
    except ValueError:
        raise HTTPException(404, "Library not found.") from None
    with get_session() as db:
        query = db.query(Source).filter(Source.library_id == resolved)
        items = query.order_by(Source.indexed_at.desc(), Source.id).offset((page - 1) * page_size).limit(page_size).all()
        return {
            "items": [{"id": s.id, "title": s.title, "url": s.url, "author": s.author, "platform": s.platform} for s in items],
            "total": query.count(), "page": page, "page_size": page_size,
        }
