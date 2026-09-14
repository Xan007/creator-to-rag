from dataclasses import dataclass
from typing import List, Optional


@dataclass
class UserInfo:

    id: str
    username: str
    created_at: float


def _repo():
    import storage.repositories as repo
    return repo


def _db():
    from storage.db import get_session
    return get_session()


def _from_model(model) -> UserInfo:
    return UserInfo(
        id=model.id,
        username=model.username,
        created_at=model.created_at or 0.0,
    )


def get_current_user_id() -> Optional[str]:
    """Return the user ID from CRAG_USER env var (username lookup)."""
    from config.env import getenv
    username = getenv("USER")
    if not username:
        return None
    user = load_user(username)
    return user.id if user else None


def resolve_user(username: Optional[str]) -> Optional["UserInfo"]:
    """Resolve a username to UserInfo, falling back to CRAG_USER env var."""
    from config.env import getenv
    name = username or getenv("USER")
    if not name:
        return None
    return load_user(name)


def load_user(username: str) -> Optional[UserInfo]:
    db = _db()
    try:
        model = _repo().get_user_by_username(db, username)
        return _from_model(model) if model else None
    finally:
        db.close()


def load_user_by_id(user_id: str) -> Optional[UserInfo]:
    db = _db()
    try:
        model = _repo().get_user_by_id(db, user_id)
        return _from_model(model) if model else None
    finally:
        db.close()


def create_user(username: str, user_id: Optional[str] = None) -> UserInfo:
    db = _db()
    try:
        model = _repo().create_user(db, username, user_id=user_id)
        return _from_model(model)
    finally:
        db.close()


def get_or_create_user(identifier: str) -> UserInfo:
    """Find a user by username or ID, or auto-create if it does not exist."""
    db = _db()
    try:
        model = _repo().get_user_by_id(db, identifier)
        if model:
            return _from_model(model)
        model = _repo().get_user_by_username(db, identifier)
        if model:
            return _from_model(model)
        model = _repo().create_user(db, username=identifier, user_id=identifier)
        return _from_model(model)
    finally:
        db.close()


def list_users() -> List[UserInfo]:
    db = _db()
    try:
        return [_from_model(m) for m in _repo().list_users(db)]
    finally:
        db.close()


def delete_user(username: str) -> bool:
    db = _db()
    try:
        user = _repo().get_user_by_username(db, username)
        if not user:
            return False
        return _repo().delete_user(db, user.id)
    finally:
        db.close()
