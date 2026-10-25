import os
import logging
import secrets
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Literal, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config.env import getenv, load_runtime_env

load_runtime_env()
from config import saved as saved_config
from config.profiles import (
    ProfileConfig,
    delete_profile,
    list_profiles,
    load_profile,
    save_profile,
)
from config.settings import (
    VALID_ANALYSIS_MODES,
    VALID_EMBED_PROVIDERS,
    VALID_ENGINES,
    AppSettings,
    load_settings,
    save_settings,
)
from config.users import (
    UserInfo,
    create_user,
    delete_user,
    get_current_user_id,
    get_or_create_user,
    list_users,
    load_user,
    load_user_by_id,
    resolve_user,
)
from src.api.jobs import manager

app = FastAPI(
    title="Creator Knowledge Library API",
    description="Build source-scoped creator knowledge libraries and query them with grounded RAG.",
    version="0.3.0",
)

_cors_origins = [o.strip() for o in (getenv("CORS_ORIGINS") or "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
# This API authenticates with headers (X-User-Id / X-API-Key), never cookies, so
# credentialed CORS is disabled on purpose: `allow_origins=["*"]` and
# `allow_credentials=True` are mutually exclusive in the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Content-Type",
        "Authorization",
        "X-User-Id",
        "X-Username",
        "X-API-Key",
    ],
    expose_headers=["X-Request-Id"],
    max_age=600,
)


@app.middleware("http")
async def protect_local_origin(request, call_next):
    origin = request.headers.get("origin")
    if origin and "*" not in _cors_origins and origin not in _cors_origins:
        return JSONResponse(status_code=403, content={"detail": "Origin is not allowed to access the local ingestion service."})
    return await call_next(request)


async def require_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    expected = getenv("API_KEY")
    if expected and not secrets.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")


class ProfileIn(BaseModel):
    username: str
    interests: str = ""
    max_posts: int = 50
    analysis_mode: str = "gemini"
    audio_only: bool = False


class ProfilePatch(BaseModel):
    interests: Optional[str] = None
    max_posts: Optional[int] = None

    analysis_mode: Optional[str] = None
    audio_only: Optional[bool] = None


class RunIn(BaseModel):
    username: str
    library_id: Optional[str] = None
    newer_than: Optional[str] = None
    keep_media: bool = False
    caption_only: bool = False
    full_media: bool = False


class AddReelIn(BaseModel):
    url: Optional[str] = None
    urls: Optional[List[str]] = None
    creator: Optional[str] = None
    library_id: Optional[str] = None
    caption_only: bool = False
    full_media: bool = False
    keep_media: bool = False

    def resolved_urls(self) -> List[str]:
        items = list(self.urls or [])
        if self.url:
            items.append(self.url)
        return [u.strip() for u in items if u and u.strip()]


class LinkPostsIn(BaseModel):
    post_ids: List[str]


class SavedProcessIn(BaseModel):
    limit: Optional[int] = None
    caption_only: bool = False
    full_media: bool = False
    workers: int = 4
    user_id: Optional[str] = None
    username: Optional[str] = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class QueryIn(BaseModel):
    question: Optional[str] = Field(default=None, max_length=8000)
    query: Optional[str] = Field(default=None, max_length=8000)
    library: Optional[str] = None
    library_id: Optional[str] = None
    creator: Optional[str] = None
    user_id: Optional[str] = None
    mode: str = "grounded_plus"
    top_k: int = 6
    min_score: float = Field(default=0.15, ge=0, le=1, allow_inf_nan=False)
    history: Optional[List[ChatTurn]] = None
    artifact_type: Optional[str] = Field(
        default=None,
        description="Optional explicit export: workout_plan, recipe_book, or grocery_list. Never inferred from the question.",
    )

    @property
    def resolved_question(self) -> str:
        """Return whichever of question/query was supplied, preferring question."""
        q = self.question or self.query or ""
        if not q.strip():
            raise ValueError("'question' (or 'query') is required and must not be empty.")
        return q.strip()


class UserIn(BaseModel):
    username: str = Field(min_length=1)
    user_id: Optional[str] = None


class LibraryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    user_id: Optional[str] = None
    username: Optional[str] = None


class LibrarySourceIn(BaseModel):
    url: Optional[str] = None
    urls: Optional[List[str]] = None
    caption_only: bool = False
    full_media: bool = False
    keep_media: bool = False
    interests: Optional[str] = None
    max_posts: Optional[int] = None

    def resolved_urls(self) -> List[str]:
        values = list(self.urls or [])
        if self.url:
            values.append(self.url)
        return [value.strip() for value in values if value and value.strip()]


async def get_current_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_username: Optional[str] = Header(None, alias="X-Username"),
) -> Optional[UserInfo]:
    """Resolve active user context from HTTP headers, environment, or single existing user."""
    identifier = x_user_id or x_username
    if identifier:
        auto_create = (getenv("AUTO_CREATE_USERS", "true") or "true").lower() in ("true", "1", "yes")
        if auto_create:
            return get_or_create_user(identifier)
        user = load_user_by_id(identifier) or load_user(identifier)
        if user:
            return user
        raise HTTPException(status_code=404, detail=f"User '{identifier}' not found.")

    env_user = resolve_user(None)
    if env_user:
        return env_user

    users = list_users()
    if len(users) == 1:
        return users[0]

    return None


def _resolve_api_user(
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = None,
) -> UserInfo:
    """Resolve user from explicit parameters, current user context, or system defaults."""
    auto_create = (getenv("AUTO_CREATE_USERS", "true") or "true").lower() in ("true", "1", "yes")
    if username:
        user = load_user(username)
        if not user and auto_create:
            user = get_or_create_user(username)
        if user:
            return user
    if user_id:
        user = load_user_by_id(user_id)
        if not user and auto_create:
            user = get_or_create_user(user_id)
        if user:
            return user
    if current_user:
        return current_user
    user = resolve_user(None)
    if user:
        return user
    users = list_users()
    if len(users) == 1:
        return users[0]
    if auto_create:
        return get_or_create_user("default")
    raise HTTPException(
        status_code=400,
        detail="User not specified and no default user found. Provide 'X-User-Id' header, 'user_id', or 'username'.",
    )


@app.get("/libraries", tags=["libraries"])
def get_libraries(
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)
    from src.pipeline import list_libraries
    return list_libraries(user.id)


@app.post("/libraries", status_code=201, tags=["libraries"])
def create_library_endpoint(
    body: LibraryIn,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    user = _resolve_api_user(user_id=body.user_id, username=body.username, current_user=current_user)
    from src.pipeline import create_library
    try:
        return create_library(user.id, body.name, body.description)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/libraries/{library_id}", tags=["libraries"])
def get_library_endpoint(
    library_id: str,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)
    from src.pipeline.library import get_library_details
    try:
        return get_library_details(user.id, library_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.patch("/libraries/{library_id}", tags=["libraries"])
def update_library_endpoint(
    library_id: str,
    body: LibraryIn,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)
    from src.pipeline.library import update_library
    try:
        return update_library(user.id, library_id, body.name, body.description)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.delete("/libraries/{library_id}", tags=["libraries"])
def delete_library_endpoint(
    library_id: str,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, str]:
    user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)
    from src.pipeline.library import delete_library
    try:
        delete_library(user.id, library_id)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.delete("/libraries/{library_id}/sources/{source_id}", tags=["libraries"])
def delete_library_source_endpoint(
    library_id: str,
    source_id: str,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, str]:
    user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)
    from src.pipeline.library import remove_source
    try:
        remove_source(user.id, library_id, source_id)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.delete("/libraries/{library_id}/posts/bulk", tags=["libraries"])
def bulk_remove_posts(
    library_id: str,
    body: LinkPostsIn,
    background_tasks: BackgroundTasks,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> JSONResponse:
    """Remove multiple posts from a library in one call.

    The posts remain in the global pool (``GET /posts``) — they are only
    de-linked from this library's Source/Chunk index.
    """
    if not body.post_ids:
        raise HTTPException(status_code=422, detail="Provide at least one post_id.")

    try:
        user = _resolve_api_user(current_user=current_user)
        from src.pipeline import resolve_library
        resolved_library_id = resolve_library(user.id, library_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    from src.pipeline.library import remove_post as _remove_post

    removed: list[str] = []
    not_found: list[str] = []
    for post_id in body.post_ids:
        try:
            _remove_post(owner_id=user.id, library_id_or_slug=resolved_library_id, post_id=post_id)
            removed.append(post_id)
        except ValueError:
            not_found.append(post_id)
        except Exception as exc:
            logging.warning("bulk_remove_posts: failed to remove %s — %s", post_id, exc)
            not_found.append(post_id)

    # Fire-and-forget: clear library_id from Pinecone metadata for removed posts
    if removed:
        def _clear_pinecone(post_ids: list[str]) -> None:
            try:
                from src.indexer.pinecone_indexer import PineconeIndexer
                idx = PineconeIndexer()
                idx.update_posts_library(post_ids=post_ids, library_id="")
            except Exception as exc:
                logging.warning("bulk_remove_posts: Pinecone update failed — %s", exc)

        background_tasks.add_task(_clear_pinecone, removed)

    return JSONResponse({
        "status": "success",
        "removed": len(removed),
        "not_found": not_found,
    })








@app.delete("/libraries/{library_id}/posts/{post_id}", tags=["libraries"])
def delete_library_post_endpoint(
    library_id: str,
    post_id: str,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, str]:
    user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)
    from src.pipeline.library import remove_post
    try:
        remove_post(user.id, library_id, post_id)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.delete("/libraries/{library_id}/profiles/{profile_username}", tags=["libraries"])
def delete_library_profile_endpoint(
    library_id: str,
    profile_username: str,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, str]:
    user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)
    from src.pipeline.library import remove_profile
    try:
        remove_profile(user.id, library_id, profile_username)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _run_pinecone_updates(post_ids: List[str], resolved_library_id: str) -> None:
    if not post_ids:
        return
    try:
        from src.indexer.pinecone_indexer import PineconeIndexer
        indexer = PineconeIndexer()
        indexer.update_posts_library(post_ids=post_ids, library_id=resolved_library_id)
    except Exception as exc:
        logging.warning("Background Pinecone metadata update failed: %s", exc)


@app.post("/libraries/{library_id}/profiles/{username}/link", tags=["libraries"])
def link_global_profile(
    library_id: str,
    username: str,
    background_tasks: BackgroundTasks,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> JSONResponse:
    try:
        user = _resolve_api_user(current_user=current_user)
        from src.pipeline import resolve_library
        resolved_library_id = resolve_library(user.id, library_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    from storage.db import get_session
    from storage.models import Post
    from src.pipeline import link_posts_to_library

    db = get_session()
    try:
        posts = db.query(Post).filter(Post.creator_username == username).all()
        if not posts:
            raise HTTPException(status_code=404, detail="No posts found for this profile. Scrape it first.")

        post_ids = [p.id for p in posts]
        linked = link_posts_to_library(db, post_ids, resolved_library_id)

        # Update Pinecone asynchronously
        background_tasks.add_task(_run_pinecone_updates, post_ids, resolved_library_id)

        return JSONResponse({"status": "success", "message": f"Linked {len(linked)} posts to library."})
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/libraries/{library_id}/posts/link", tags=["libraries"])
def link_global_posts(
    library_id: str,
    body: LinkPostsIn,
    background_tasks: BackgroundTasks,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> JSONResponse:
    if not body.post_ids:
        raise HTTPException(status_code=422, detail="Provide at least one post_id to link.")

    try:
        user = _resolve_api_user(current_user=current_user)
        from src.pipeline import resolve_library
        resolved_library_id = resolve_library(user.id, library_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    from storage.db import get_session
    from src.pipeline import link_posts_to_library

    db = get_session()
    try:
        linked = link_posts_to_library(db, body.post_ids, resolved_library_id)
        if not linked:
            raise HTTPException(status_code=404, detail="None of the specified posts were found.")

        background_tasks.add_task(_run_pinecone_updates, linked, resolved_library_id)
        return JSONResponse({"status": "success", "message": f"Linked {len(linked)} posts to library."})
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/libraries/{library_id}/sources", status_code=202, tags=["libraries"])
def add_library_sources(
    library_id: str,
    body: LibrarySourceIn,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> JSONResponse:
    urls = body.resolved_urls()
    if not urls:
        raise HTTPException(status_code=422, detail="Provide 'url' or 'urls'.")
    try:
        user = _resolve_api_user(current_user=current_user)
        from src.pipeline import resolve_library
        resolved_library_id = resolve_library(user.id, library_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    from src.pipeline import ingest_urls
    return _submit(
        "library-ingest",
        ingest_urls,
        library_id=resolved_library_id,
        owner_id=user.id,
        urls=urls,
        caption_only=body.caption_only,
        full_media=body.full_media,
        keep_media=body.keep_media,
        interests=body.interests,
        max_posts=body.max_posts,
    )


@app.get("/health", tags=["meta"])
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/config", tags=["config"])
def get_config(_: None = Depends(require_api_key)) -> Dict[str, Any]:
    return vars(load_settings())


@app.patch("/config", tags=["config"])
def patch_config(patch: Dict[str, Any], _: None = Depends(require_api_key)) -> Dict[str, Any]:
    settings = load_settings()
    allowed = {"audio_only", "engine", "embed_provider"}
    for key, value in patch.items():
        if key not in allowed:
            raise HTTPException(status_code=422, detail=f"Unknown setting '{key}'.")
        if key == "engine" and value not in VALID_ENGINES:
            raise HTTPException(status_code=422, detail=f"engine must be one of {sorted(VALID_ENGINES)}.")
        if key == "embed_provider" and value not in VALID_EMBED_PROVIDERS:
            raise HTTPException(status_code=422, detail=f"embed_provider must be one of {sorted(VALID_EMBED_PROVIDERS)}.")
        setattr(settings, key, value)
    save_settings(settings)
    return vars(load_settings())


@app.get("/config/cookies", tags=["config"])
def get_cookies_status(_: None = Depends(require_api_key)) -> Dict[str, Any]:
    cookies_path = os.getenv("IG_COOKIES_FILE", "cookies.txt")
    exists = os.path.exists(cookies_path)
    size = os.path.getsize(cookies_path) if exists else 0
    return {"exists": exists, "size_bytes": size}


@app.post("/config/cookies", tags=["config"])
async def upload_cookies(
    file: UploadFile = File(...),
    _: None = Depends(require_api_key)
) -> Dict[str, Any]:
    cookies_path = os.getenv("IG_COOKIES_FILE", "cookies.txt")
    try:
        content = await file.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise HTTPException(status_code=413, detail="Cookies file exceeds 1 MiB.")
        with open(cookies_path, "wb") as f:
            f.write(content)
        return {"status": "success", "message": "Cookies uploaded successfully.", "size_bytes": len(content)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/config/cookies", tags=["config"])
def delete_cookies(_: None = Depends(require_api_key)) -> Dict[str, Any]:
    cookies_path = os.getenv("IG_COOKIES_FILE", "cookies.txt")
    if os.path.exists(cookies_path):
        try:
            os.remove(cookies_path)
            return {"status": "success", "message": "Cookies deleted successfully."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"status": "success", "message": "No cookies file found."}



def _profile_to_dict(p: ProfileConfig, post_count: Optional[int] = None) -> Dict[str, Any]:
    cnt = post_count if post_count is not None else len(p.processed_ids)
    return {
        "username": p.username,
        "interests": p.interests,
        "max_posts": p.max_posts,
        "analysis_mode": p.analysis_mode,
        "audio_only": p.audio_only,
        "processed_count": cnt,
        "total_posts_scraped": cnt,
        "total_posts": cnt,
        "failed_ids": p.failed_ids,
    }


@app.get("/posts", tags=["posts"])
def get_posts(
    page: int = 1,
    page_size: int = 50,
    creator: Optional[str] = None,
    library_id: Optional[str] = None,
    unlinked_only: bool = False,
    query: Optional[str] = None,
    search_mode: str = "keyword",
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    from storage.db import get_session
    from storage.models import Post
    from sqlalchemy import or_

    if page < 1:
        page = 1
    page_size = max(1, min(page_size, 200))

    db = get_session()
    try:
        import re

        def _get_clean_topic(k: Optional[str], default: str) -> str:
            if k:
                m = re.search(r"##\s*Topic\s*[:\n\- ]*([^\n#]+)", k, re.IGNORECASE)
                if m:
                    topic = m.group(1).strip().strip('"\'').rstrip(".").lstrip("#* ")
                    if topic:
                        return topic
            return default or ""

        is_desc = (sort_order.lower() == "desc")

        # Semantic vector search mode
        if search_mode == "semantic" and query and query.strip():
            from src.search.semantic_search import search_posts_semantic
            semantic_results = search_posts_semantic(
                query_text=query.strip(),
                db=db,
                creator=creator,
                library_id=library_id,
                unlinked_only=unlinked_only,
                top_k=200,
            )

            # Apply explicit sorting if user clicked a column header
            if sort_by == "date":
                semantic_results.sort(
                    key=lambda x: (x[0].published_at or x[0].indexed_at or 0),
                    reverse=is_desc,
                )
            elif sort_by == "creator":
                semantic_results.sort(
                    key=lambda x: (x[0].creator_username or "").lower(),
                    reverse=is_desc,
                )
            elif sort_by in ("reel", "title"):
                semantic_results.sort(
                    key=lambda x: _get_clean_topic(x[0].extracted_knowledge, x[0].title).lower(),
                    reverse=is_desc,
                )
            else:
                # Default for semantic search: preserve similarity score order (relevance order)
                semantic_results.sort(key=lambda x: x[1], reverse=is_desc)

            total = len(semantic_results)
            offset = (page - 1) * page_size
            paginated = semantic_results[offset : offset + page_size]
            return {
                "items": [
                    {
                        "id": p.id,
                        "url": p.url,
                        "creator_username": p.creator_username,
                        "type": p.type,
                        "title": _get_clean_topic(p.extracted_knowledge, p.title),
                        "description": p.description,
                        "extracted_knowledge": p.extracted_knowledge,
                        "published_at": p.published_at,
                        "indexed_at": p.indexed_at,
                        "library_id": p.library_id,
                        "score": round(score, 3),
                    }
                    for p, score in paginated
                ],
                "total": total,
                "page": page,
                "page_size": page_size,
                "search_mode": "semantic",
            }

        # Keyword / structured syntax mode
        q = db.query(Post)
        if creator:
            q = q.filter(Post.creator_username == creator)
        if unlinked_only:
            q = q.filter(or_(Post.library_id == None, Post.library_id == ""))
        elif library_id:
            q = q.filter(Post.library_id == library_id)
        if query:
            from src.search.query_parser import apply_search_filters
            q = apply_search_filters(q, query, Post)

        total = q.count()
        offset = (page - 1) * page_size

        if sort_by == "creator":
            order_clause = Post.creator_username.desc() if is_desc else Post.creator_username.asc()
            q = q.order_by(order_clause.nullslast())
        elif sort_by in ("reel", "title"):
            order_clause = Post.title.desc() if is_desc else Post.title.asc()
            q = q.order_by(order_clause.nullslast())
        else:
            # Default or sort_by == "date"
            if is_desc:
                q = q.order_by(Post.published_at.desc().nullslast(), Post.indexed_at.desc().nullslast())
            else:
                q = q.order_by(Post.published_at.asc().nullslast(), Post.indexed_at.asc().nullslast())

        posts = q.offset(offset).limit(page_size).all()

        return {
            "items": [
                {
                    "id": p.id,
                    "url": p.url,
                    "creator_username": p.creator_username,
                    "type": p.type,
                    "title": _get_clean_topic(p.extracted_knowledge, p.title),
                    "description": p.description,
                    "extracted_knowledge": p.extracted_knowledge,
                    "published_at": p.published_at,
                    "indexed_at": p.indexed_at,
                    "library_id": p.library_id,
                }
                for p in posts
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "search_mode": "keyword",
        }
    finally:
        db.close()


@app.delete("/posts/{post_id}", tags=["posts"])
def delete_post_endpoint(
    post_id: str,
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """Permanently delete a post from the global pool, including its chunks, sources, and vectors."""
    from src.pipeline.library import delete_global_posts
    deleted = delete_global_posts([post_id])
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Post not found.")
    return {"status": "deleted", "post_id": post_id, "deleted_count": deleted}


@app.delete("/posts", tags=["posts"])
def bulk_delete_posts_endpoint(
    body: LinkPostsIn,
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """Permanently delete multiple posts from the global database in one request."""
    if not body.post_ids:
        raise HTTPException(status_code=422, detail="Provide at least one post_id.")
    from src.pipeline.library import delete_global_posts
    deleted = delete_global_posts(body.post_ids)
    return {"status": "deleted", "deleted_count": deleted, "post_ids": body.post_ids}



@app.get("/sources", tags=["sources"])
def get_sources(
    library_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """List sources, optionally filtered by library_id."""
    from storage.db import get_session
    from storage.models import Source

    page_size = max(1, min(page_size, 200))
    page = max(1, page)
    db = get_session()
    try:
        q = db.query(Source)
        if library_id:
            q = q.filter(Source.library_id == library_id)
        total = q.count()
        sources = q.order_by(Source.indexed_at.desc().nullslast()).offset((page - 1) * page_size).limit(page_size).all()
        return {
            "items": [
                {
                    "id": s.id,
                    "library_id": s.library_id,
                    "platform": s.platform,
                    "url": s.url,
                    "author": s.author,
                    "title": s.title,
                    "status": s.status,
                    "ingest_status": s.ingest_status,
                    "published_at": s.published_at,
                    "indexed_at": s.indexed_at,
                    "post_id": s.id.split(":")[-1] if ":" in (s.id or "") else None,
                }
                for s in sources
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    finally:
        db.close()


@app.post("/sources/{source_id}/reindex", tags=["sources"])
def reindex_source(
    source_id: str,
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """Re-analyze a source with Gemini AI and regenerate structured knowledge, topic title, chunks, and embeddings."""
    import time
    from storage.db import get_session
    import storage.repositories as repo
    from storage.models import Source, Post
    from src.analyzer.gemini_analyzer import GeminiAnalyzer
    from src.analyzer.title_generator import extract_topic_from_knowledge
    from src.indexer.pinecone_indexer import PineconeIndexer

    db = get_session()
    try:
        clean_id = source_id.strip()
        if clean_id.startswith("post-"):
            clean_id = clean_id[5:]
        elif clean_id.startswith("source-"):
            clean_id = clean_id[7:]

        # 1. Direct source lookup
        source = repo.get_source(db, clean_id)

        # 2. Direct post lookup
        post = repo.get_post(db, clean_id)

        # 3. If no source, check via post.source_id or suffix or URL
        if not source and post and post.source_id:
            source = repo.get_source(db, post.source_id)

        if not source:
            source = db.query(Source).filter(Source.id.like(f"%:{clean_id}")).first()

        if not source:
            if "/" in clean_id:
                source = db.query(Source).filter(Source.url == clean_id).first()
            if not source:
                source = db.query(Source).filter(Source.url.like(f"%/{clean_id}/%")).first()

        # 4. If no post, check via URL or source.id suffix
        if not post:
            if "/" in clean_id:
                post = db.query(Post).filter(Post.url == clean_id).first()
            if not post:
                post = db.query(Post).filter(Post.url.like(f"%/{clean_id}/%")).first()

        if not post and source:
            if ":" in source.id:
                post_candidate_id = source.id.split(":", 1)[1]
                post = repo.get_post(db, post_candidate_id)
            if not post and source.url:
                post = db.query(Post).filter(Post.url == source.url).first()

        if not source and not post:
            raise HTTPException(status_code=404, detail=f"Source or post '{source_id}' not found")

        # Resolve raw caption/description to analyze
        raw_text = ""
        if source and source.description:
            raw_text = source.description
        elif post and post.description:
            raw_text = post.description
        elif post and post.extracted_knowledge:
            raw_text = post.extracted_knowledge
        elif source and source.extracted_text:
            raw_text = source.extracted_text

        if not raw_text.strip():
            raise HTTPException(
                status_code=400,
                detail="No caption or description content available to re-analyze for this item."
            )

        analyzer = GeminiAnalyzer()
        extracted = analyzer.extract_knowledge([], raw_text)
        clean_title = extract_topic_from_knowledge(extracted)
        if not clean_title:
            clean_title = (source.title if source and source.title else "") or (post.title if post and post.title else "")

        indexer = PineconeIndexer()

        # Find all sources that correspond to this item (e.g. across multiple libraries)
        matching_sources = []
        if source:
            matching_sources.append(source)

        item_post_id = post.id if post else (source.id.split(":", 1)[1] if ":" in source.id else clean_id)
        other_sources = db.query(Source).filter(Source.id.like(f"%:{item_post_id}")).all()
        for s in other_sources:
            if s.id not in [x.id for x in matching_sources]:
                matching_sources.append(s)

        for s in matching_sources:
            s.title = clean_title or s.title
            s.extracted_text = extracted
            s.status = "indexed"
            s.ingest_status = "full_indexed"
            db.commit()

            indexer.index_source(
                source_id=s.id,
                library_id=s.library_id or "",
                url=s.url or (post.url if post else ""),
                platform=s.platform or "instagram",
                author=s.author or (post.creator_username if post else ""),
                title=clean_title or s.title,
                description=s.description or raw_text,
                extracted_text=extracted,
                ingest_status="full_indexed",
            )

        if post:
            post.title = clean_title or post.title
            post.extracted_knowledge = extracted
            post.indexed_at = time.time()
            db.commit()

            indexer.index_post(
                post_id=post.id,
                url=post.url or (source.url if source else ""),
                creator_username=post.creator_username or (source.author if source else ""),
                post_type=post.type or "Post",
                description=post.description or raw_text,
                extracted_text=extracted,
                library_id=post.library_id or (source.library_id if source else None),
                ingest_status="full_indexed",
                published_at=post.published_at,
            )

        return {
            "status": "success",
            "source_id": source.id if source else (post.id if post else source_id),
            "title": clean_title,
            "extracted_knowledge": extracted,
        }
    finally:
        db.close()


@app.get("/libraries/{library_id}/sources", tags=["libraries"])
def get_library_sources(
    library_id: str,
    page: int = 1,
    page_size: int = 50,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """List sources belonging to a specific library."""
    user = _resolve_api_user(current_user=current_user)
    from storage.db import get_session
    from storage.models import Source
    from src.pipeline import resolve_library

    try:
        resolved_lib_id = resolve_library(user.id, library_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    page_size = max(1, min(page_size, 200))
    page = max(1, page)
    db = get_session()
    try:
        q = db.query(Source).filter(Source.library_id == resolved_lib_id)
        total = q.count()
        sources = q.order_by(Source.indexed_at.desc().nullslast()).offset((page - 1) * page_size).limit(page_size).all()
        return {
            "items": [
                {
                    "id": s.id,
                    "library_id": s.library_id,
                    "platform": s.platform,
                    "url": s.url,
                    "author": s.author,
                    "title": s.title,
                    "status": s.status,
                    "ingest_status": s.ingest_status,
                    "published_at": s.published_at,
                    "indexed_at": s.indexed_at,
                    "post_id": s.id.split(":")[-1] if ":" in (s.id or "") else None,
                }
                for s in sources
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    finally:
        db.close()


@app.get("/profiles", tags=["profiles"])
def get_profiles(_: None = Depends(require_api_key)) -> List[Dict[str, Any]]:
    from storage.db import get_session
    from storage.models import Post
    from sqlalchemy import func

    db = get_session()
    counts: Dict[str, int] = {}
    try:
        grouped = db.query(Post.creator_username, func.count(Post.id)).group_by(Post.creator_username).all()
        counts = {user: cnt for user, cnt in grouped if user}
    finally:
        db.close()

    result = []
    seen = set()
    for username in list_profiles():
        p = load_profile(username)
        if p:
            cnt = counts.get(p.username, 0)
            result.append(_profile_to_dict(p, post_count=cnt))
            seen.add(p.username.lower())

    for creator_username, cnt in counts.items():
        if creator_username.lower() not in seen:
            result.append({
                "username": creator_username,
                "interests": "",
                "max_posts": 50,
                "analysis_mode": "gemini",
                "audio_only": False,
                "processed_count": cnt,
                "total_posts_scraped": cnt,
                "total_posts": cnt,
                "failed_ids": [],
            })
    return result


@app.post("/profiles", status_code=201, tags=["profiles"])
def create_or_update_profile(body: ProfileIn, _: None = Depends(require_api_key)) -> Dict[str, Any]:
    if body.analysis_mode not in VALID_ANALYSIS_MODES:
        raise HTTPException(status_code=422, detail=f"analysis_mode must be one of {sorted(VALID_ANALYSIS_MODES)}.")
    profile = load_profile(body.username)
    existed = profile is not None
    if profile is None:
        profile = ProfileConfig(username=body.username)
    profile.interests = body.interests
    profile.max_posts = body.max_posts
    profile.analysis_mode = body.analysis_mode
    profile.audio_only = body.audio_only
    save_profile(profile)
    data = _profile_to_dict(profile)
    data["updated_existing"] = existed
    return data


@app.get("/profiles/{username}", tags=["profiles"])
def get_profile(username: str, _: None = Depends(require_api_key)) -> Dict[str, Any]:
    profile = load_profile(username)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile @{username} not found.")
    return _profile_to_dict(profile)


@app.patch("/profiles/{username}", tags=["profiles"])
def patch_profile(username: str, body: ProfilePatch, _: None = Depends(require_api_key)) -> Dict[str, Any]:
    profile = load_profile(username)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile @{username} not found.")
    if body.analysis_mode is not None:
        if body.analysis_mode not in VALID_ANALYSIS_MODES:
            raise HTTPException(status_code=422, detail=f"analysis_mode must be one of {sorted(VALID_ANALYSIS_MODES)}.")
        profile.analysis_mode = body.analysis_mode
    if body.interests is not None:
        profile.interests = body.interests
    if body.max_posts is not None:
        profile.max_posts = body.max_posts
    if body.audio_only is not None:
        profile.audio_only = body.audio_only
    save_profile(profile)
    return _profile_to_dict(profile)


@app.delete("/profiles/{username}", tags=["profiles"])
def remove_profile(username: str, _: None = Depends(require_api_key)) -> Dict[str, str]:
    if not delete_profile(username):
        raise HTTPException(status_code=404, detail=f"Profile @{username} not found.")
    return {"deleted": username}


@app.post("/profiles/{username}/reset", tags=["profiles"])
def reset_profile(username: str, _: None = Depends(require_api_key)) -> Dict[str, Any]:
    profile = load_profile(username)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile @{username} not found.")
    cleared = len(profile.processed_ids) + len(profile.failed_ids)
    profile.processed_ids = []
    profile.failed_ids = []
    save_profile(profile)
    return {"reset": username, "cleared": cleared}


@app.get("/users", tags=["users"])
def get_users(_: None = Depends(require_api_key)) -> List[Dict[str, Any]]:
    return [{"id": u.id, "username": u.username, "created_at": u.created_at} for u in list_users()]


@app.post("/users", status_code=201, tags=["users"])
def create_new_user(body: UserIn, _: None = Depends(require_api_key)) -> Dict[str, Any]:
    existing = load_user(body.username)
    if existing:
        raise HTTPException(status_code=409, detail=f"User '{body.username}' already exists.")
    user = create_user(body.username)
    return {"id": user.id, "username": user.username, "created_at": user.created_at}


@app.get("/users/{username}", tags=["users"])
def get_user_details(username: str, _: None = Depends(require_api_key)) -> Dict[str, Any]:
    user = load_user(username) or load_user_by_id(username)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")
    return {"id": user.id, "username": user.username, "created_at": user.created_at}


@app.delete("/users/{username}", tags=["users"])
def remove_user(username: str, _: None = Depends(require_api_key)) -> Dict[str, str]:
    if not delete_user(username):
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")
    return {"deleted": username}


def _submit(kind: str, fn, **fn_kwargs) -> JSONResponse:
    job = manager.submit(kind, fn, **fn_kwargs)
    return JSONResponse(status_code=202, content={"job_id": job.id, "status_url": f"/jobs/{job.id}"})


@app.post("/jobs/run", status_code=202, tags=["jobs"])
def job_run(
    body: RunIn,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key)
) -> JSONResponse:
    from src.pipeline import run_profile

    profile = load_profile(body.username)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile @{body.username} not found. Create it via POST /profiles.")

    resolved_library_id = None
    if body.library_id:
        user = _resolve_api_user(current_user=current_user)
        from src.pipeline import resolve_library
        try:
            resolved_library_id = resolve_library(user.id, body.library_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    return _submit(
        "run",
        run_profile,
        username=body.username,
        library_id=resolved_library_id,
        newer_than=body.newer_than,
        keep_media=body.keep_media,
        caption_only=body.caption_only,
        full_media=body.full_media,
        interests=profile.interests,
        max_posts=profile.max_posts,
        analysis_mode=profile.analysis_mode,
    )


@app.post("/jobs/add-reel", status_code=202, tags=["jobs"])
def job_add_reel(
    body: AddReelIn,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> JSONResponse:
    from src.pipeline import add_reel

    urls = body.resolved_urls()
    if not urls:
        raise HTTPException(status_code=422, detail="Provide 'url' (string) or 'urls' (list of strings).")

    resolved_library_id = None
    if body.library_id:
        user = _resolve_api_user(current_user=current_user)
        from src.pipeline import resolve_library
        try:
            resolved_library_id = resolve_library(user.id, body.library_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    return _submit(
        "add-reel",
        add_reel,
        urls=urls,
        creator=body.creator,
        library_id=resolved_library_id,
        caption_only=body.caption_only,
        full_media=body.full_media,
        keep_media=body.keep_media,
    )


@app.post("/jobs/saved-process", status_code=202, tags=["jobs"])
def job_saved_process(
    body: SavedProcessIn,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> JSONResponse:
    from src.pipeline import process_saved

    user = _resolve_api_user(user_id=body.user_id, username=body.username, current_user=current_user)
    return _submit(
        "saved-process",
        process_saved,
        user_id=user.id,
        limit=body.limit,
        caption_only=body.caption_only,
        full_media=body.full_media,
        workers=body.workers,
    )


@app.post("/jobs/{job_id}/cancel", tags=["jobs"])
def cancel_job(job_id: str, _: None = Depends(require_api_key)) -> Dict[str, Any]:
    success = manager.cancel(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or cannot be cancelled")
    return {"status": "cancelled"}

@app.get("/jobs", tags=["jobs"])
def list_jobs(
    include_log: bool = False,
    log_limit: int = 20,
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    current = manager.current()
    jobs = []
    for j in manager.all_jobs():
        data = j.to_dict(include_log=include_log, log_limit=log_limit)
        if j.status == "queued" and current is not None:
            data["queued_behind"] = current.id
            data["note"] = f"Serialized worker busy with job {current.id} ({current.kind}); this job starts when it finishes."
        jobs.append(data)
    return {
        "worker": {"current_job": current.id, "kind": current.kind} if current else {"current_job": None, "idle": True},
        "jobs": jobs,
    }


@app.get("/jobs/{job_id}", tags=["jobs"])
def get_job(job_id: str, log_limit: int = 200, _: None = Depends(require_api_key)) -> Dict[str, Any]:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict(log_limit=log_limit)


@app.post("/saved/import", tags=["saved"])
def saved_import(
    file: UploadFile = File(...),
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    suffix = Path(file.filename or "export.zip").suffix.lower()
    if suffix not in (".zip", ".json"):
        raise HTTPException(status_code=422, detail="Upload a .zip export or a saved_posts.json file.")

    user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)

    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as tmp:
            total_bytes = 0
            while chunk := file.file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > 50 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Saved export exceeds 50 MiB.")
                tmp.write(chunk)
        from src.pipeline.saved import import_user_saved_posts
        import_res = import_user_saved_posts(user.id, Path(tmp_path))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        os.unlink(tmp_path)

    from storage.db import get_session
    import storage.repositories as repo
    db = get_session()
    try:
        s_model = repo.get_user_saved_state(db, user.id)
        return {
            "user_id": user.id,
            "total": s_model.total,
            "imported_at": s_model.imported_at,
            "source": s_model.source,
            "processed": len(s_model.processed_ids or []),
            "failed": len(s_model.failed_ids or []),
            "new_saved": import_res.get("new_saved", 0),
        }
    finally:
        db.close()


@app.get("/saved/status", tags=["saved"])
def saved_status(
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    try:
        user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)
        from storage.db import get_session
        import storage.repositories as repo
        db = get_session()
        try:
            state = repo.get_user_saved_state(db, user.id)
            if state.total == 0:
                return {"imported": False, "user_id": user.id}
            return {
                "imported": True,
                "user_id": user.id,
                "total": state.total,
                "imported_at": state.imported_at,
                "source": state.source,
                "processed": len(state.processed_ids or []),
                "failed": len(state.failed_ids or []),
                "pending": max(state.total - len(state.processed_ids or []), 0),
                "failed_ids": state.failed_ids or [],
            }
        finally:
            db.close()
    except HTTPException:
        state = saved_config.load_state()
        if state.total == 0:
            return {"imported": False}
        return {
            "imported": True,
            "total": state.total,
            "imported_at": state.imported_at,
            "source": state.source,
            "processed": len(state.processed_ids),
            "failed": len(state.failed_ids),
            "pending": max(state.total - len(state.processed_ids), 0),
            "failed_ids": state.failed_ids,
        }


@app.post("/saved/reset", tags=["saved"])
def saved_reset(
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    try:
        user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)
        from storage.db import get_session
        import storage.repositories as repo
        db = get_session()
        try:
            state = repo.get_user_saved_state(db, user.id)
            cleared = len(state.processed_ids or []) + len(state.failed_ids or [])
            state.processed_ids = []
            state.failed_ids = []
            repo.save_user_saved_state(db, state)
            return {"cleared": cleared, "user_id": user.id}
        finally:
            db.close()
    except HTTPException:
        state = saved_config.load_state()
        cleared = len(state.processed_ids) + len(state.failed_ids)
        state.processed_ids = []
        state.failed_ids = []
        saved_config.save_state(state)
        return {"cleared": cleared}


@app.post("/query", tags=["rag"])
def query(
    body: QueryIn,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """Grounded RAG query.

    mode='grounded_plus' (default) answers from creator content and may append
    a clearly labeled general-knowledge block. mode='strict' never leaves the
    creators' content.

    Accepts either ``question`` or ``query`` as the question field (both are supported).
    """
    # Resolve question (accepts both "question" and "query" field names)
    try:
        resolved_q = body.resolved_question
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if body.mode not in ("strict", "grounded_plus"):
        raise HTTPException(status_code=422, detail="mode must be 'strict' or 'grounded_plus'.")
    if not 1 <= body.top_k <= 20:
        raise HTTPException(status_code=422, detail="top_k must be between 1 and 20.")
    if not 0 <= body.min_score <= 1:
        raise HTTPException(status_code=422, detail="min_score must be between 0 and 1.")

    history_dicts = None
    if body.history is not None:
        if len(body.history) > 12:
            raise HTTPException(status_code=422, detail="history supports at most 12 messages.")
        history_dicts = [{"role": t.role, "content": t.content} for t in body.history]

    from src.pipeline import query_knowledge

    try:
        kwargs = {
            "top_k": body.top_k,
            "min_score": body.min_score,
            "mode": body.mode,
            "history": history_dicts,
        }
        library_identifier = body.library or body.library_id
        if library_identifier:
            user = _resolve_api_user(current_user=current_user)
            from src.pipeline import resolve_library
            try:
                kwargs["library_id"] = resolve_library(user.id, library_identifier)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
            kwargs["user_id"] = user.id
        if body.user_id:
            kwargs["user_id"] = body.user_id
        if body.artifact_type:
            kwargs["artifact_type"] = body.artifact_type

        return query_knowledge(
            resolved_q,
            body.creator,
            **kwargs,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Query failed: {e}")

@app.post("/chats/title", tags=["rag"])
def generate_chat_title(body: ChatTurn, _: None = Depends(require_api_key)) -> Dict[str, str]:
    from src.llm.factory import LLMClientFactory
    llm = LLMClientFactory.get_client()
    prompt = f"Genera un título muy corto (máximo 4 palabras) para esta conversación basándote en este mensaje. No uses comillas. Mensaje: {body.content}"
    try:
        title = llm.generate([{"role": "user", "content": prompt}], temperature=0.3)
        return {"title": title.strip().strip('"').strip("'")}
    except Exception as e:
        return {"title": "New Chat"}


import os
if os.path.exists('data/raw'):
    app.mount('/media', StaticFiles(directory='data/raw'), name='media')
