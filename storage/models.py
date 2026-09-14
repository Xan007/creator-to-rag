from datetime import datetime, timezone
import time
from typing import Optional

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    created_at = Column(Float, default=time.time)


class Library(Base):
    """A user's curated knowledge space, independent of source platform."""

    __tablename__ = "libraries"

    id = Column(String, primary_key=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    description = Column(Text, default="")
    created_at = Column(Float, default=time.time)

    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_library_owner_name"),
    )


class Source(Base):
    """A canonical piece of creator content (post, video, PDF, lesson, etc.)."""

    __tablename__ = "sources"

    id = Column(String, primary_key=True)
    library_id = Column(String, ForeignKey("libraries.id"), nullable=False, index=True)
    platform = Column(String, nullable=False, default="url")
    content_type = Column(String, nullable=False, default="video")
    url = Column(String, nullable=False, default="")
    author = Column(String, default="")
    title = Column(String, default="")
    description = Column(Text, default="")
    extracted_text = Column(Text, default="")
    status = Column(String, default="indexed")
    ingest_status = Column(String, default="full_indexed")
    content_hash = Column(String, default="")
    chunk_version = Column(String, default="v1")
    embedding_provider = Column(String, default="")
    embedding_model = Column(String, default="")
    embedding_dimension = Column(Integer, nullable=True)
    created_at = Column(Float, default=time.time)
    indexed_at = Column(Float, nullable=True)


class LibrarySource(Base):
    """Many-to-many membership between canonical sources and libraries."""

    __tablename__ = "library_sources"

    library_id = Column(String, ForeignKey("libraries.id"), primary_key=True)
    source_id = Column(String, ForeignKey("sources.id"), primary_key=True)
    added_at = Column(Float, default=time.time)


class Chunk(Base):
    """Retrieval unit belonging to a source."""

    __tablename__ = "chunks"

    id = Column(String, primary_key=True)
    source_id = Column(String, ForeignKey("sources.id"), nullable=False, index=True)
    library_id = Column(String, ForeignKey("libraries.id"), nullable=False, index=True)
    ordinal = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False, default="")
    token_count = Column(Integer, default=0)
    chunk_version = Column(String, default="v1")
    created_at = Column(Float, default=time.time)


class IGProfile(Base):
    __tablename__ = "ig_profiles"

    username = Column(String, primary_key=True)
    last_scraped_at = Column(Float, nullable=True, default=None)
    last_run_at = Column(String, nullable=True, default=None)
    total_posts_scraped = Column(Integer, default=0)
    interests = Column(String, default="")
    max_posts = Column(Integer, default=50)
    processed_ids = Column(JSON, default=list)
    failed_ids = Column(JSON, default=list)
    analysis_mode = Column(String, default="gemini")
    audio_only = Column(Boolean, default=False)


Profile = IGProfile


class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True)
    url = Column(String, default="")
    creator_username = Column(String, default="")
    type = Column(String, default="Post")
    description = Column(Text, default="")
    extracted_knowledge = Column(Text, default="")
    indexed_at = Column(Float, nullable=True)
    library_id = Column(String, nullable=True, index=True)
    source_id = Column(String, nullable=True, index=True)


ProcessedPost = Post


class Group(Base):
    __tablename__ = "groups"

    id = Column(String, primary_key=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    created_at = Column(Float, default=time.time)

    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_group_owner_name"),
    )


class GroupPost(Base):
    __tablename__ = "group_posts"

    group_id = Column(String, ForeignKey("groups.id"), primary_key=True)
    post_id = Column(String, ForeignKey("posts.id"), primary_key=True)
    added_at = Column(Float, default=time.time)


class GroupShare(Base):
    __tablename__ = "group_shares"

    group_id = Column(String, ForeignKey("groups.id"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)


class UserSavedPost(Base):
    __tablename__ = "user_saved_posts"

    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    post_id = Column(String, ForeignKey("posts.id"), primary_key=True)
    saved_at = Column(Float, default=time.time)
    source_url = Column(String, default="")


SavedPost = UserSavedPost


class UserSavedState(Base):
    __tablename__ = "user_saved_states"

    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    total = Column(Integer, default=0)
    imported_at = Column(String, default="")
    source = Column(String, default="")
    processed_ids = Column(JSON, default=list)
    failed_ids = Column(JSON, default=list)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(JSON)


class JobRecord(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False)
    status = Column(String, default="queued")
    created_at = Column(Float, default=time.time)
    started_at = Column(Float, nullable=True)
    finished_at = Column(Float, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    log = Column(JSON, default=list)

