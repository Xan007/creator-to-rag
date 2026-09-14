import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config.env import getenv
from config import saved as saved_config
from config.groups import (
    GroupInfo,
    add_post_to_group,
    create_group,
    delete_group,
    get_post_ids_in_group,
    load_group,
    load_group_by_name,
    list_groups_for_user,
    remove_post_from_group,
    share_group,
    unshare_group,
)
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

_cors_origins = [o.strip() for o in (getenv("CORS_ORIGINS") or "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


async def require_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    expected = getenv("API_KEY")
    if expected and x_api_key != expected:
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


class AddReelIn(BaseModel):
    url: Optional[str] = None
    urls: Optional[List[str]] = None
    creator: Optional[str] = None
    caption_only: bool = False
    keep_media: bool = False

    def resolved_urls(self) -> List[str]:
        items = list(self.urls or [])
        if self.url:
            items.append(self.url)
        return [u.strip() for u in items if u and u.strip()]


class SavedProcessIn(BaseModel):
    limit: Optional[int] = None
    caption_only: bool = False
    workers: int = 4
    user_id: Optional[str] = None
    username: Optional[str] = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class QueryIn(BaseModel):
    question: str
    library: Optional[str] = None
    library_id: Optional[str] = None
    creator: Optional[str] = None
    group_name: Optional[str] = None
    user_id: Optional[str] = None
    mode: str = "grounded_plus"
    top_k: int = 6
    min_score: float = 0.35
    history: Optional[List[ChatTurn]] = None
    artifact_type: Optional[str] = Field(
        default=None,
        description="Optional explicit export: workout_plan, recipe_book, or grocery_list. Never inferred from the question.",
    )


class UserIn(BaseModel):
    username: str = Field(min_length=1)
    user_id: Optional[str] = None


class GroupIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    user_id: Optional[str] = None
    username: Optional[str] = None


class GroupPostIn(BaseModel):
    post_id: Optional[str] = None
    url: Optional[str] = None
    creator: Optional[str] = None
    interests: Optional[str] = None


class GroupShareIn(BaseModel):
    target_username: Optional[str] = None
    target_user_id: Optional[str] = None


class LibraryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    user_id: Optional[str] = None
    username: Optional[str] = None


class LibrarySourceIn(BaseModel):
    url: Optional[str] = None
    urls: Optional[List[str]] = None
    caption_only: bool = False
    keep_media: bool = False

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
        keep_media=body.keep_media,
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


def _profile_to_dict(p: ProfileConfig) -> Dict[str, Any]:
    return {
        "username": p.username,
        "interests": p.interests,
        "max_posts": p.max_posts,
        "analysis_mode": p.analysis_mode,
        "audio_only": p.audio_only,
        "processed_count": len(p.processed_ids),
        "failed_ids": p.failed_ids,
    }


@app.get("/profiles", tags=["profiles"])
def get_profiles(_: None = Depends(require_api_key)) -> List[Dict[str, Any]]:
    result = []
    for username in list_profiles():
        p = load_profile(username)
        if p:
            result.append(_profile_to_dict(p))
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


@app.get("/groups", tags=["groups"])
def get_groups(
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    user = _resolve_api_user(user_id=user_id, username=username, current_user=current_user)
    groups = list_groups_for_user(user.id)
    return [
        {
            "id": g.id,
            "owner_id": g.owner_id,
            "name": g.name,
            "description": g.description,
            "created_at": g.created_at,
            "post_count": g.post_count,
            "shared_with": g.shared_with,
        }
        for g in groups
    ]


@app.post("/groups", status_code=201, tags=["groups"])
def create_new_group(
    body: GroupIn,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    user = _resolve_api_user(user_id=body.user_id, username=body.username, current_user=current_user)
    existing = load_group_by_name(user.id, body.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Group '{body.name}' already exists for user '{user.username}'.")
    g = create_group(user.id, body.name, body.description)
    return {
        "id": g.id,
        "owner_id": g.owner_id,
        "name": g.name,
        "description": g.description,
        "created_at": g.created_at,
        "post_count": g.post_count,
        "shared_with": g.shared_with,
    }


@app.get("/groups/{group_id}", tags=["groups"])
def get_group_details(group_id: str, _: None = Depends(require_api_key)) -> Dict[str, Any]:
    g = load_group(group_id)
    if not g:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found.")
    return {
        "id": g.id,
        "owner_id": g.owner_id,
        "name": g.name,
        "description": g.description,
        "created_at": g.created_at,
        "post_count": g.post_count,
        "shared_with": g.shared_with,
        "post_ids": get_post_ids_in_group(group_id),
    }


@app.delete("/groups/{group_id}", tags=["groups"])
def remove_group(group_id: str, _: None = Depends(require_api_key)) -> Dict[str, str]:
    if not delete_group(group_id):
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found.")
    return {"deleted": group_id}


@app.post("/groups/{group_id}/posts", tags=["groups"])
def add_post_to_group_endpoint(
    group_id: str,
    body: GroupPostIn,
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    g = load_group(group_id)
    if not g:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found.")

    if body.creator:
        from src.pipeline.group import populate_group_from_profile
        try:
            res = populate_group_from_profile(g.owner_id, g.name, body.creator, interests=body.interests)
            return {"status": "ok", "group_id": group_id, "result": res}
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    if body.url:
        from src.pipeline import add_reel
        try:
            add_reel([body.url], group_id=group_id)
            return {"status": "ok", "group_id": group_id, "url": body.url}
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Failed to add reel: {e}")

    if body.post_id:
        added = add_post_to_group(group_id, body.post_id)
        return {"status": "ok", "group_id": group_id, "post_id": body.post_id, "added": added}

    raise HTTPException(status_code=422, detail="Provide 'post_id', 'url', or 'creator'.")


@app.delete("/groups/{group_id}/posts/{post_id}", tags=["groups"])
def remove_post_from_group_endpoint(
    group_id: str,
    post_id: str,
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    g = load_group(group_id)
    if not g:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found.")
    removed = remove_post_from_group(group_id, post_id)
    return {"group_id": group_id, "post_id": post_id, "removed": removed}


@app.post("/groups/{group_id}/share", tags=["groups"])
def share_group_endpoint(
    group_id: str,
    body: GroupShareIn,
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    g = load_group(group_id)
    if not g:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found.")

    target_user = None
    if body.target_username:
        target_user = load_user(body.target_username)
    elif body.target_user_id:
        target_user = load_user_by_id(body.target_user_id)

    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found.")

    shared = share_group(group_id, target_user.id)
    return {"group_id": group_id, "target_user_id": target_user.id, "shared": shared}


@app.delete("/groups/{group_id}/share/{user_id}", tags=["groups"])
def unshare_group_endpoint(
    group_id: str,
    user_id: str,
    _: None = Depends(require_api_key),
) -> Dict[str, Any]:
    g = load_group(group_id)
    if not g:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found.")

    unshared = unshare_group(group_id, user_id)
    return {"group_id": group_id, "unshared_user_id": user_id, "unshared": unshared}


def _submit(kind: str, fn, **fn_kwargs) -> JSONResponse:
    job = manager.submit(kind, fn, **fn_kwargs)
    return JSONResponse(status_code=202, content={"job_id": job.id, "status_url": f"/jobs/{job.id}"})


@app.post("/jobs/run", status_code=202, tags=["jobs"])
def job_run(body: RunIn, _: None = Depends(require_api_key)) -> JSONResponse:
    from src.pipeline import run_profile

    if not load_profile(body.username):
        raise HTTPException(status_code=404, detail=f"Profile @{body.username} not found. Create it via POST /profiles.")
    return _submit(
        "run",
        run_profile,
        username=body.username,
        library_id=body.library_id,
        newer_than=body.newer_than,
        keep_media=body.keep_media,
    )


@app.post("/jobs/add-reel", status_code=202, tags=["jobs"])
def job_add_reel(body: AddReelIn, _: None = Depends(require_api_key)) -> JSONResponse:
    from src.pipeline import add_reel

    urls = body.resolved_urls()
    if not urls:
        raise HTTPException(status_code=422, detail="Provide 'url' (string) or 'urls' (list of strings).")
    return _submit(
        "add-reel",
        add_reel,
        urls=urls,
        creator=body.creator,
        caption_only=body.caption_only,
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
        workers=body.workers,
    )


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
async def saved_import(
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
            shutil.copyfileobj(file.file, tmp)
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
    """
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
        if body.group_name:
            kwargs["group_name"] = body.group_name
            resolved_uid = body.user_id or (current_user.id if current_user else None)
            if resolved_uid:
                kwargs["user_id"] = resolved_uid
        elif body.user_id:
            kwargs["user_id"] = body.user_id
        if body.artifact_type:
            kwargs["artifact_type"] = body.artifact_type

        return query_knowledge(
            body.question,
            body.creator,
            **kwargs,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Query failed: {e}")


