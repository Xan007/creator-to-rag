from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class ProfileConfig:
    username: str = ""
    interests: str = ""
    max_posts: int = 50
    processed_ids: List[str] = field(default_factory=list)
    analysis_mode: str = "gemini"
    audio_only: bool = False
    failed_ids: List[str] = field(default_factory=list)
    total_posts_scraped: int = 0
    last_scraped_at: Optional[float] = None
    last_run_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def _repo():
    import storage.repositories as repo
    return repo


def _db():
    from storage.db import get_session
    return get_session()


def _to_model(profile: ProfileConfig):
    from storage.models import IGProfile
    return IGProfile(
        username=profile.username,
        interests=profile.interests,
        max_posts=profile.max_posts,
        processed_ids=profile.processed_ids,
        analysis_mode=profile.analysis_mode,
        audio_only=profile.audio_only,
        failed_ids=profile.failed_ids,
        total_posts_scraped=profile.total_posts_scraped,
        last_scraped_at=profile.last_scraped_at,
        last_run_at=profile.last_run_at,
    )


def _from_model(model) -> ProfileConfig:
    return ProfileConfig(
        username=model.username,
        interests=model.interests or "",
        max_posts=model.max_posts or 50,
        processed_ids=list(model.processed_ids or []),
        analysis_mode=model.analysis_mode or "gemini",
        audio_only=bool(model.audio_only),
        failed_ids=list(model.failed_ids or []),
        total_posts_scraped=getattr(model, "total_posts_scraped", 0) or 0,
        last_scraped_at=getattr(model, "last_scraped_at", None),
        last_run_at=getattr(model, "last_run_at", None),
    )


def load_profile(username: str) -> Optional[ProfileConfig]:
    db = _db()
    try:
        model = _repo().get_ig_profile(db, username)
        return _from_model(model) if model else None
    finally:
        db.close()


def save_profile(profile: ProfileConfig) -> None:
    db = _db()
    try:
        model = _to_model(profile)
        _repo().upsert_ig_profile(db, model)
    finally:
        db.close()


def list_profiles() -> List[str]:
    db = _db()
    try:
        return [p.username for p in _repo().list_ig_profiles(db)]
    finally:
        db.close()


def delete_profile(username: str) -> bool:
    db = _db()
    try:
        return _repo().delete_ig_profile(db, username)
    finally:
        db.close()


# Compatibility aliases for legacy IGProfileInfo callers
IGProfileInfo = ProfileConfig
load_ig_profile = load_profile
save_ig_profile = save_profile
delete_ig_profile = delete_profile
