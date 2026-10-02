import time
import re
from typing import List, Optional
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import text

from storage.models import (
    Chunk,
    IGProfile,
    LibrarySource,
    Library,
    Post,
    Source,
    Setting,
    User,
    UserSavedPost,
    UserSavedState,
)


def _new_uuid() -> str:
    return str(uuid.uuid4())


def get_setting(db: Session, key: str) -> Optional[dict]:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


def set_setting(db: Session, key: str, value: dict) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def get_all_settings(db: Session) -> dict:
    return {row.key: row.value for row in db.query(Setting).all()}


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def list_users(db: Session) -> List[User]:
    return db.query(User).all()


def create_user(db: Session, username: str, user_id: Optional[str] = None) -> User:
    user = User(id=user_id or _new_uuid(), username=username, created_at=time.time())
    db.add(user)
    db.commit()
    db.refresh(user)
    if not get_library_by_name(db, user.id, "Mi biblioteca"):
        create_library(db, user.id, "Mi biblioteca", "Biblioteca personal")
    return user


def get_library(db: Session, library_id: str) -> Optional[Library]:
    return db.query(Library).filter(Library.id == library_id).first()


def get_library_by_name(db: Session, owner_id: str, name: str) -> Optional[Library]:
    return db.query(Library).filter(Library.owner_id == owner_id, Library.name == name).first()


def slugify_library_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")
    return slug or "library"


def get_library_by_slug(db: Session, owner_id: str, slug: str) -> Optional[Library]:
    return db.query(Library).filter(Library.owner_id == owner_id, Library.slug == slug).first()


def resolve_library(db: Session, owner_id: str, identifier: str) -> Optional[Library]:
    return get_library_by_slug(db, owner_id, identifier) or get_library(db, identifier)


def list_libraries(db: Session, owner_id: Optional[str] = None) -> List[Library]:
    query = db.query(Library)
    if owner_id:
        query = query.filter(Library.owner_id == owner_id)
    return query.order_by(Library.created_at.asc()).all()


def create_library(db: Session, owner_id: str, name: str, description: str = "") -> Library:
    base_slug = slugify_library_name(name)
    slug = base_slug
    suffix = 2
    while get_library_by_slug(db, owner_id, slug):
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    library = Library(
        id=_new_uuid(),
        owner_id=owner_id,
        name=name.strip(),
        slug=slug,
        description=description,
    )
    db.add(library)
    db.commit()
    db.refresh(library)
    return library


def get_source(db: Session, source_id: str) -> Optional[Source]:
    return db.query(Source).filter(Source.id == source_id).first()


def get_source_by_url(db: Session, library_id: str, url: str) -> Optional[Source]:
    return (
        db.query(Source)
        .join(LibrarySource, LibrarySource.source_id == Source.id)
        .filter(LibrarySource.library_id == library_id, Source.url == url)
        .first()
    )


def list_sources_by_ids(db: Session, source_ids: List[str]) -> List[Source]:
    if not source_ids:
        return []
    return db.query(Source).filter(Source.id.in_(source_ids)).all()


def list_caption_indexed_post_ids(
    db: Session,
    library_id: str,
    creator_username: Optional[str] = None,
) -> List[str]:
    """Instagram source ids are `{library_id}:{post_id}`."""
    query = db.query(Source).filter(
        Source.library_id == library_id,
        Source.ingest_status == "caption_indexed",
        Source.platform == "instagram",
    )
    if creator_username:
        query = query.filter(Source.author == creator_username)
    prefix = f"{library_id}:"
    post_ids = []
    for source in query.all():
        if source.id.startswith(prefix):
            post_ids.append(source.id[len(prefix):])
        elif source.url:
            post_ids.append(source.id)
    return post_ids



def add_source_to_library(db: Session, library_id: str, source_id: str) -> bool:
    existing = (
        db.query(LibrarySource)
        .filter(LibrarySource.library_id == library_id, LibrarySource.source_id == source_id)
        .first()
    )
    if existing:
        return False
    db.add(LibrarySource(library_id=library_id, source_id=source_id, added_at=time.time()))
    if db.bind and db.bind.dialect.name == "sqlite":
        source = get_source(db, source_id)
        chunks = db.query(Chunk).filter(Chunk.source_id == source_id).all()
        if source:
            for chunk in chunks:
                db.execute(
                    text(
                        "INSERT INTO chunks_fts(chunk_id, library_id, text, title, author, description, url) "
                        "VALUES (:chunk_id, :library_id, :text, :title, :author, :description, :url)"
                    ),
                    {
                        "chunk_id": chunk.id,
                        "library_id": library_id,
                        "text": chunk.text,
                        "title": source.title or "",
                        "author": source.author or "",
                        "description": source.description or "",
                        "url": source.url or "",
                    },
                )
    db.commit()
    return True


def upsert_source(db: Session, source: Source) -> Source:
    existing = get_source(db, source.id)
    if existing:
        for field in ("library_id", "platform", "content_type", "url", "author", "title",
                      "description", "extracted_text", "status", "ingest_status",
                      "content_hash", "chunk_version", "embedding_provider",
                      "embedding_model", "embedding_dimension", "indexed_at"):
            value = getattr(source, field, None)
            if field != "library_id" and value not in (None, ""):
                setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        if source.library_id:
            add_source_to_library(db, source.library_id, existing.id)
        return existing
    db.add(source)
    db.commit()
    db.refresh(source)
    if source.library_id:
        add_source_to_library(db, source.library_id, source.id)
    return source


def replace_chunks(db: Session, source_id: str, library_id: str, chunks: List[Chunk]) -> None:
    db.query(Chunk).filter(Chunk.source_id == source_id).delete()
    db.add_all(chunks)
    if str(db.bind.dialect.name) == "sqlite":
        source = get_source(db, source_id)
        if source:
            memberships = [
                row.library_id
                for row in db.query(LibrarySource).filter(LibrarySource.source_id == source_id).all()
            ] or [library_id]
            for member_library_id in memberships:
                db.execute(
                    text("DELETE FROM chunks_fts WHERE chunk_id LIKE :prefix AND library_id = :library_id"),
                    {"prefix": f"{source_id}:%", "library_id": member_library_id},
                )
                for chunk in chunks:
                    db.execute(
                        text(
                            "INSERT INTO chunks_fts(chunk_id, library_id, text, title, author, description, url) "
                            "VALUES (:chunk_id, :library_id, :text, :title, :author, :description, :url)"
                        ),
                        {
                            "chunk_id": chunk.id,
                            "library_id": member_library_id,
                            "text": chunk.text,
                            "title": source.title or "",
                            "author": source.author or "",
                            "description": source.description or "",
                            "url": source.url or "",
                        },
                    )
    db.commit()
    try:
        from src.rag.lexical import LexicalRetriever
        LexicalRetriever.invalidate(library_id)
    except ImportError:
        pass


def list_chunks(db: Session, library_id: str, source_ids: Optional[List[str]] = None) -> List[Chunk]:
    query = (
        db.query(Chunk)
        .join(LibrarySource, LibrarySource.source_id == Chunk.source_id)
        .filter(LibrarySource.library_id == library_id)
    )
    if source_ids is not None:
        if not source_ids:
            return []
        query = query.filter(Chunk.source_id.in_(source_ids))
    return query.order_by(Chunk.source_id, Chunk.ordinal).all()


def list_sources(db: Session, library_id: str) -> List[Source]:
    return (
        db.query(Source)
        .join(LibrarySource, LibrarySource.source_id == Source.id)
        .filter(LibrarySource.library_id == library_id)
        .order_by(Source.created_at.asc())
        .all()
    )



def delete_user(db: Session, user_id: str) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True


def get_ig_profile(db: Session, username: str) -> Optional[IGProfile]:
    return db.query(IGProfile).filter(IGProfile.username == username).first()


def list_ig_profiles(db: Session) -> List[IGProfile]:
    return db.query(IGProfile).all()


def upsert_ig_profile(db: Session, profile: IGProfile) -> IGProfile:
    existing = get_ig_profile(db, profile.username)
    if existing:
        if profile.last_scraped_at is not None:
            existing.last_scraped_at = profile.last_scraped_at
        if profile.last_run_at is not None:
            existing.last_run_at = profile.last_run_at
        if profile.total_posts_scraped is not None:
            existing.total_posts_scraped = profile.total_posts_scraped
        if profile.interests is not None:
            existing.interests = profile.interests
        if profile.max_posts is not None:
            existing.max_posts = profile.max_posts
        if profile.processed_ids is not None:
            existing.processed_ids = profile.processed_ids
        if profile.failed_ids is not None:
            existing.failed_ids = profile.failed_ids
        if profile.analysis_mode is not None:
            existing.analysis_mode = profile.analysis_mode
        if profile.audio_only is not None:
            existing.audio_only = profile.audio_only
        db.commit()
        db.refresh(existing)
        return existing
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def delete_ig_profile(db: Session, username: str) -> bool:
    profile = get_ig_profile(db, username)
    if not profile:
        return False
    db.delete(profile)
    db.commit()
    return True


get_profile = get_ig_profile
list_profiles = list_ig_profiles
upsert_profile = upsert_ig_profile
delete_profile = delete_ig_profile


def get_post(db: Session, post_id: str) -> Optional[Post]:
    return db.query(Post).filter(Post.id == post_id).first()


def upsert_post(db: Session, post: Post) -> Post:
    existing = get_post(db, post.id)
    if existing:
        existing.url = post.url or existing.url
        existing.creator_username = post.creator_username or existing.creator_username
        existing.type = post.type or existing.type
        existing.description = post.description or existing.description
        existing.extracted_knowledge = post.extracted_knowledge or existing.extracted_knowledge
        existing.library_id = post.library_id or existing.library_id
        existing.source_id = post.source_id or existing.source_id
        if post.indexed_at is not None:
            existing.indexed_at = post.indexed_at
        db.commit()
        db.refresh(existing)
        return existing
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


get_processed_post = get_post
upsert_processed_post = upsert_post


def list_posts(db: Session, creator_username: Optional[str] = None) -> List[Post]:
    q = db.query(Post)
    if creator_username:
        q = q.filter(Post.creator_username == creator_username)
    return q.all()


def count_posts(db: Session, creator_username: Optional[str] = None) -> int:
    q = db.query(Post)
    if creator_username:
        q = q.filter(Post.creator_username == creator_username)
    return q.count()


def get_all_post_ids(db: Session, creator_username: Optional[str] = None) -> List[str]:
    q = db.query(Post.id)
    if creator_username:
        q = q.filter(Post.creator_username == creator_username)
    return [row[0] for row in q.all()]


def add_user_saved_post(db: Session, user_id: str, post_id: str, source_url: str = "") -> bool:
    existing = (
        db.query(UserSavedPost)
        .filter(UserSavedPost.user_id == user_id, UserSavedPost.post_id == post_id)
        .first()
    )
    if existing:
        return False
    db.add(UserSavedPost(user_id=user_id, post_id=post_id, saved_at=time.time(), source_url=source_url))
    db.commit()
    return True


def get_user_saved_post_ids(db: Session, user_id: str) -> List[str]:
    return [
        row.post_id
        for row in db.query(UserSavedPost).filter(UserSavedPost.user_id == user_id).all()
    ]


def count_user_saved_posts(db: Session, user_id: str) -> int:
    return db.query(UserSavedPost).filter(UserSavedPost.user_id == user_id).count()


def get_user_saved_state(db: Session, user_id: str) -> UserSavedState:
    state = db.query(UserSavedState).filter(UserSavedState.user_id == user_id).first()
    if not state:
        state = UserSavedState(user_id=user_id)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def save_user_saved_state(db: Session, state: UserSavedState) -> None:
    db.commit()


def get_saved_state(db: Session, user_id: str = "default") -> UserSavedState:
    return get_user_saved_state(db, user_id)


def save_saved_state(db: Session, state: UserSavedState) -> None:
    save_user_saved_state(db, state)


def upsert_saved_posts_bulk(db: Session, posts: List[UserSavedPost]) -> None:
    for p in posts:
        existing = (
            db.query(UserSavedPost)
            .filter(UserSavedPost.user_id == p.user_id, UserSavedPost.post_id == p.post_id)
            .first()
        )
        if not existing:
            db.add(p)
    db.commit()


from storage.models import JobRecord

def get_job(db: Session, job_id: str) -> Optional[JobRecord]:
    return db.query(JobRecord).filter(JobRecord.id == job_id).first()

def create_job(db: Session, job_id: str, kind: str) -> JobRecord:
    job = JobRecord(id=job_id, kind=kind, created_at=time.time())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

def update_job(db: Session, job: JobRecord) -> None:
    db.commit()

def list_jobs(db: Session) -> List[JobRecord]:
    return db.query(JobRecord).order_by(JobRecord.created_at.desc()).all()

def append_job_log(db: Session, job_id: str, message: str) -> None:
    job = get_job(db, job_id)
    if job:
        logs = list(job.log or [])
        entry = f"[{time.strftime('%H:%M:%S')}] {message}"
        logs.append(entry)
        job.log = logs
        db.commit()
