"""Product-level ingestion into a user's library."""

import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.connectors.url import extract_url_source
from src.pipeline._common import Progress, download_with_ytdlp, echo, locked_progress, post_step
from storage.db import get_session
import storage.repositories as repo

logger = logging.getLogger(__name__)


def _source_id(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:32]


def create_library(owner_id: str, name: str, description: str = "") -> Dict[str, Any]:
    db = get_session()
    try:
        existing = repo.get_library_by_name(db, owner_id, name)
        if existing:
            return {"id": existing.id, "slug": existing.slug, "name": existing.name, "created": False}
        library = repo.create_library(db, owner_id, name, description)
        return {"id": library.id, "slug": library.slug, "name": library.name, "created": True}
    finally:
        db.close()


def list_libraries(owner_id: str) -> List[Dict[str, Any]]:
    db = get_session()
    try:
        return [
            {"id": item.id, "slug": item.slug, "name": item.name, "description": item.description, "created_at": item.created_at}
            for item in repo.list_libraries(db, owner_id)
        ]
    finally:
        db.close()


def resolve_library(owner_id: str, identifier: Optional[str] = None) -> str:
    """Resolve a slug/UUID, creating a friendly default library when needed."""
    db = get_session()
    try:
        if identifier:
            library = repo.resolve_library(db, owner_id, identifier)
            if not library:
                raise ValueError(f"Library '{identifier}' not found for this user.")
            return library.id
        libraries = repo.list_libraries(db, owner_id)
        if libraries:
            return libraries[0].id
        return repo.create_library(db, owner_id, "Mi biblioteca", "Biblioteca personal").id
    finally:
        db.close()


def ingest_urls(
    library_id: str,
    urls: List[str],
    *,
    owner_id: Optional[str] = None,
    caption_only: bool = False,
    keep_media: bool = False,
    full_media: bool = False,
    interests: Optional[str] = None,
    max_posts: Optional[int] = None,
    progress: Progress = echo,
) -> Dict[str, Any]:
    """Index arbitrary public videos using one source pipeline."""
    from config.settings import load_settings
    from src.indexer.pinecone_indexer import PineconeIndexer

    progress = locked_progress(progress)

    if not urls:
        raise ValueError("At least one URL is required.")
    if owner_id:
        db = get_session()
        try:
            library = repo.get_library(db, library_id)
            if not library or library.owner_id != owner_id:
                raise ValueError("You do not have access to this library.")
        finally:
            db.close()
    settings = load_settings()
    if settings.engine == "gemini":
        from src.analyzer.gemini_analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer()
    elif settings.engine in {"local_whisper", "openai_whisper"}:
        from src.analyzer.whisper_analyzer import WhisperAnalyzer

        analyzer = WhisperAnalyzer(mode=settings.engine)
    else:
        raise ValueError(f"Unsupported analysis engine: {settings.engine}")
    indexer = PineconeIndexer()
    unique_urls = list(dict.fromkeys(u.strip() for u in urls if u and u.strip()))
    if not unique_urls:
        raise ValueError("At least one non-empty URL is required.")
    total_urls = len(unique_urls)

    def ingest_one(position: int, url: str) -> Dict[str, Any]:
        files = []
        sid = _source_id(url)

        def step(message: str) -> None:
            progress(post_step(position, total_urls, sid[:8], message))

        try:
            source = extract_url_source(url)
            sid = _source_id(url)
            
            if interests:
                from src.filter.interest_filter import InterestFilter
                step("Filtering by interests...")
                fake_desc = source.description or source.title or ""
                fake_post = {"id": sid, "description": fake_desc, "caption": fake_desc}
                kept = filter_instance.filter_batch([fake_post], interests)
                if sid not in kept:
                    step("Skipped: Did not match interests")
                    return {
                        "added": [],
                        "failed": [],
                        "skipped": [{"url": url, "reason": "interest filter"}]
                    }

            db = get_session()
            try:
                existing = repo.get_source_by_url(db, library_id, source.url)
                if existing and existing.status == "indexed":
                    already_full = existing.ingest_status != "caption_indexed"
                    if already_full or not full_media:
                        progress(post_step(position, total_urls, sid[:8], "already indexed, skipping"))
                        return {
                            "added": [{
                                "source_id": existing.id,
                                "url": url,
                                "platform": source.platform,
                                "chunks": 0,
                                "already_indexed": True,
                            }],
                            "failed": [],
                        }
            finally:
                db.close()
            from src.analyzer.caption_triage import resolve_ingest_plan

            should_download, ingest_status = resolve_ingest_plan(
                description=source.description or "",
                caption_only=caption_only,
                full_media=full_media,
                platform=source.platform,
            )
            if should_download:
                step(f"downloading {source.platform}...")
                files = download_with_ytdlp(url, sid, prefix=source.platform) or []
                if files and analyzer:
                    if settings.engine == "gemini":
                        extracted = analyzer.extract_knowledge(
                            files, source.description, progress=step
                        )
                    else:
                        extracted = analyzer.extract_knowledge(files, source.description)
                else:
                    extracted = (
                        analyzer.extract_knowledge([], source.description)
                        if analyzer
                        else source.description
                    )
            else:
                step("caption-only — skipping download, extracting knowledge with AI")
                extracted = (
                    analyzer.extract_knowledge([], source.description, progress=step)
                    if analyzer and source.description
                    else (source.description or "")
                )
            from src.analyzer.title_generator import extract_topic_from_knowledge
            post_title = extract_topic_from_knowledge(extracted) or source.title
            chunks = indexer.index_source(
                source_id=sid,
                library_id=library_id,
                url=source.url,
                platform=source.platform,
                author=source.author,
                title=post_title,
                description=source.description,
                extracted_text=extracted,
                ingest_status=ingest_status,
            )
            return {
                "added": [{"source_id": sid, "url": url, "platform": source.platform, "chunks": chunks}],
                "failed": [],
            }
        except Exception as exc:
            # Profile/channel URLs often cannot be downloaded as one video.
            # Ask the configured low-cost Apify actor for child video URLs.
            try:
                from src.connectors.apify_social import ApifySocialConnector
                platform = "tiktok" if "tiktok.com" in url else ""
                if platform:
                    connector = ApifySocialConnector()
                    discovered = getattr(connector, platform)([url], limit=max_posts or 20)
                    nested = ingest_urls(
                        library_id,
                        [item.url for item in discovered],
                        owner_id=owner_id,
                        caption_only=caption_only,
                        keep_media=keep_media,
                        full_media=full_media,
                        interests=interests,
                        max_posts=max_posts,
                        progress=progress,
                    )
                    return nested
            except Exception as fallback_exc:
                exc = fallback_exc
            progress(post_step(position, total_urls, sid[:8], f"failed: {exc}"))
            return {"added": [], "failed": [{"url": url, "error": str(exc)}]}
        finally:
            if files and not keep_media:
                from src.downloader.media_downloader import MediaDownloader
                MediaDownloader().cleanup_items(files)

    worker_count = max(1, min(4, int(os.getenv("INGEST_WORKERS", "3"))))
    added, failed = [], []
    with ThreadPoolExecutor(max_workers=min(worker_count, total_urls)) as executor:
        futures = [
            executor.submit(ingest_one, position, url)
            for position, url in enumerate(unique_urls, 1)
        ]
        for future in as_completed(futures):
            result = future.result()
            added.extend(result["added"])
            failed.extend(result["failed"])
    return {"added": added, "failed": failed}

def update_library(owner_id: str, library_id_or_slug: str, name: str, description: str = "") -> Dict[str, Any]:
    db = get_session()
    try:
        lib = repo.get_library_by_slug(db, owner_id, library_id_or_slug)
        if not lib:
            lib = db.query(repo.Library).filter(repo.Library.id == library_id_or_slug, repo.Library.owner_id == owner_id).first()
        if not lib:
            raise ValueError("Library not found")
        
        lib.name = name
        if description:
            lib.description = description
        db.commit()
        return {"id": lib.id, "slug": lib.slug, "name": lib.name, "description": lib.description}
    finally:
        db.close()

def delete_library(owner_id: str, library_id_or_slug: str) -> bool:
    db = get_session()
    try:
        lib = repo.get_library_by_slug(db, owner_id, library_id_or_slug)
        if not lib:
            lib = db.query(repo.Library).filter(repo.Library.id == library_id_or_slug, repo.Library.owner_id == owner_id).first()
        if not lib:
            raise ValueError("Library not found")
            
        # Delete from Pinecone
        try:
            from src.indexer.pinecone_indexer import PineconeIndexer
            indexer = PineconeIndexer()
            indexer.delete_library(lib.id)
        except Exception as e:
            logger.warning("Pinecone library deletion notice: %s", e)
            
        # Delete from DB
        db.query(repo.LibrarySource).filter(repo.LibrarySource.library_id == lib.id).delete()
        db.query(repo.Chunk).filter(repo.Chunk.library_id == lib.id).delete()
        # Unlink posts so they remain in the global pool (GET /posts)
        db.query(repo.Post).filter(repo.Post.library_id == lib.id).update({repo.Post.library_id: None})
        from sqlalchemy import text
        try:
            db.execute(text("DELETE FROM chunks_fts WHERE library_id = :lid"), {"lid": lib.id})
        except Exception:
            pass
        db.delete(lib)
        db.commit()
        return True
    finally:
        db.close()

def get_library_details(owner_id: str, library_id_or_slug: str) -> Dict[str, Any]:
    db = get_session()
    try:
        lib = repo.get_library_by_slug(db, owner_id, library_id_or_slug)
        if not lib:
            lib = db.query(repo.Library).filter(repo.Library.id == library_id_or_slug, repo.Library.owner_id == owner_id).first()
        if not lib:
            raise ValueError("Library not found")
            
        sources = db.query(repo.Source).join(repo.LibrarySource).filter(repo.LibrarySource.library_id == lib.id).all()
        library_sources = db.query(repo.LibrarySource).filter(repo.LibrarySource.library_id == lib.id).all()
        source_pids = [ls.source_id.split(":")[-1] for ls in library_sources if ls.source_id]
        from sqlalchemy import or_
        posts = db.query(repo.Post).filter(
            or_(
                repo.Post.library_id == lib.id,
                repo.Post.id.in_(source_pids)
            )
        ).all()
        
        return {
            "id": lib.id,
            "slug": lib.slug,
            "name": lib.name,
            "description": lib.description,
            "owner_id": lib.owner_id,
            "created_at": lib.created_at,
            "sources": [
                {
                    "id": s.id,
                    "platform": s.platform,
                    "url": s.url,
                    "author": s.author,
                    "title": s.title,
                    "status": s.status,
                    "ingest_status": s.ingest_status,
                    "published_at": s.published_at,
                    "indexed_at": s.indexed_at,
                }
                for s in sources
            ],
            "posts": [
                {
                    "id": p.id,
                    "url": p.url,
                    "creator_username": p.creator_username,
                    "type": p.type,
                    "title": p.title,
                    "description": p.description,
                    "extracted_knowledge": p.extracted_knowledge,
                    "published_at": p.published_at,
                    "indexed_at": p.indexed_at,
                }
                for p in posts
            ],
        }
    finally:
        db.close()

def remove_source(owner_id: str, library_id_or_slug: str, source_id: str) -> bool:
    db = get_session()
    try:
        lib = repo.get_library_by_slug(db, owner_id, library_id_or_slug)
        if not lib:
            lib = db.query(repo.Library).filter(repo.Library.id == library_id_or_slug, repo.Library.owner_id == owner_id).first()
        if not lib:
            raise ValueError("Library not found")
            
        try:
            from src.indexer.pinecone_indexer import PineconeIndexer
            indexer = PineconeIndexer()
            indexer.delete_source(source_id, library_id=lib.id)
        except Exception as e:
            logger.warning("Pinecone source deletion notice: %s", e)

        db.query(repo.LibrarySource).filter(repo.LibrarySource.library_id == lib.id, repo.LibrarySource.source_id == source_id).delete()
        db.query(repo.Chunk).filter(repo.Chunk.library_id == lib.id, repo.Chunk.source_id == source_id).delete()
        from sqlalchemy import text
        try:
            db.execute(text("DELETE FROM chunks_fts WHERE chunk_id LIKE :prefix AND library_id = :lid"), {"prefix": f"{source_id}:%", "lid": lib.id})
        except Exception:
            pass
        db.commit()
        from src.rag.lexical import LexicalRetriever
        LexicalRetriever.invalidate(lib.id)
        return True
    finally:
        db.close()

def remove_post(owner_id: str, library_id_or_slug: str, post_id: str) -> bool:
    db = get_session()
    try:
        lib = repo.get_library_by_slug(db, owner_id, library_id_or_slug)
        if not lib:
            lib = db.query(repo.Library).filter(repo.Library.id == library_id_or_slug, repo.Library.owner_id == owner_id).first()
        if not lib:
            raise ValueError("Library not found")
            
        # Delete from Pinecone
        try:
            from src.indexer.pinecone_indexer import PineconeIndexer
            indexer = PineconeIndexer()
            indexer.delete_post(post_id, library_id=lib.id)
        except Exception as e:
            logger.warning("Pinecone post deletion notice: %s", e)
            
        source_id = f"{lib.id}:{post_id}"
        db.query(repo.LibrarySource).filter(repo.LibrarySource.library_id == lib.id, repo.LibrarySource.source_id == source_id).delete()
        db.query(repo.Chunk).filter(repo.Chunk.library_id == lib.id, repo.Chunk.source_id == source_id).delete()
        # Unlink the post from this library instead of deleting from the global Post table
        post = db.query(repo.Post).filter(repo.Post.id == post_id).first()
        if post and post.library_id == lib.id:
            post.library_id = None
        from sqlalchemy import text
        try:
            db.execute(text("DELETE FROM chunks_fts WHERE chunk_id LIKE :prefix AND library_id = :lid"), {"prefix": f"{source_id}:%", "lid": lib.id})
            db.execute(text("DELETE FROM chunks_fts WHERE chunk_id LIKE :prefix AND library_id = :lid"), {"prefix": f"{post_id}:%", "lid": lib.id})
        except Exception:
            pass
        db.commit()
        from src.rag.lexical import LexicalRetriever
        LexicalRetriever.invalidate(lib.id)
        return True
    finally:
        db.close()

def remove_profile(owner_id: str, library_id_or_slug: str, profile_username: str) -> bool:
    db = get_session()
    try:
        lib = repo.get_library_by_slug(db, owner_id, library_id_or_slug)
        if not lib:
            lib = db.query(repo.Library).filter(repo.Library.id == library_id_or_slug, repo.Library.owner_id == owner_id).first()
        if not lib:
            raise ValueError("Library not found")
            
        posts = db.query(repo.Post).filter(repo.Post.library_id == lib.id, repo.Post.creator_username == profile_username).all()
        post_ids = [p.id for p in posts]
        if post_ids:
            try:
                from src.indexer.pinecone_indexer import PineconeIndexer
                indexer = PineconeIndexer()
                indexer.delete_posts(post_ids, library_id=lib.id)
            except Exception as e:
                logger.warning("Pinecone profile posts deletion notice: %s", e)
            
            for pid in post_ids:
                source_id = f"{lib.id}:{pid}"
                db.query(repo.LibrarySource).filter(repo.LibrarySource.library_id == lib.id, repo.LibrarySource.source_id == source_id).delete()
                db.query(repo.Chunk).filter(repo.Chunk.library_id == lib.id, repo.Chunk.source_id == source_id).delete()
            # Unlink posts from this library, do NOT delete them from global Post catalog
            db.query(repo.Post).filter(repo.Post.library_id == lib.id, repo.Post.creator_username == profile_username).update({repo.Post.library_id: None})
            from sqlalchemy import text
            try:
                for pid in post_ids:
                    db.execute(text("DELETE FROM chunks_fts WHERE chunk_id LIKE :prefix AND library_id = :lid"), {"prefix": f"{lib.id}:{pid}:%", "lid": lib.id})
                    db.execute(text("DELETE FROM chunks_fts WHERE chunk_id LIKE :prefix AND library_id = :lid"), {"prefix": f"{pid}:%", "lid": lib.id})
            except Exception:
                pass
            db.commit()
            from src.rag.lexical import LexicalRetriever
            LexicalRetriever.invalidate(lib.id)
        return True
    finally:
        db.close()


def link_posts_to_library(db: Any, post_ids: List[str], library_id: str) -> List[str]:
    """Links existing global posts into a specific library, creating Source, LibrarySource,
    Chunk and chunks_fts records so that library-scoped search and RAG retrieve them."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from src.analyzer.title_generator import generate_post_title
    from src.rag.chunking import chunk_text
    from src.rag.lexical import LexicalRetriever
    from storage.models import Chunk, Post, Source

    posts = db.query(Post).filter(Post.id.in_(post_ids)).all()
    if not posts:
        return []

    # Prevent duplication: skip posts that are already linked to this library
    library_sources = db.query(repo.LibrarySource).filter(repo.LibrarySource.library_id == library_id).all()
    already_linked_pids = {ls.source_id.split(":")[-1] for ls in library_sources if ls.source_id}
    posts_to_link = [p for p in posts if p.id not in already_linked_pids]
    if not posts_to_link:
        return [p.id for p in posts]
    posts = posts_to_link

    # ------------------------------------------------------------------
    # Step 1: Generate titles concurrently for posts that lack one.
    # ------------------------------------------------------------------
    posts_needing_titles = [p for p in posts if not (p.title or "").strip()]

    if posts_needing_titles:
        def _generate(post: Post) -> tuple[str, str]:
            title = generate_post_title(
                description=post.description or "",
                extracted_knowledge=post.extracted_knowledge or "",
                creator_username=post.creator_username or "",
            )
            return post.id, title

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(_generate, p): p for p in posts_needing_titles}
            title_map: dict[str, str] = {}
            for future in as_completed(futures):
                try:
                    pid, title = future.result()
                    title_map[pid] = title
                except Exception as exc:
                    logger.warning("link_posts_to_library: title generation failed — %s", exc)

        for post in posts_needing_titles:
            if post.id in title_map:
                post.title = title_map[post.id]

    # ------------------------------------------------------------------
    # Step 2: Create/update Source, LibrarySource, and Chunk records.
    # ------------------------------------------------------------------
    linked_ids: List[str] = []
    for post in posts:
        post.library_id = library_id
        source_id = f"{library_id}:{post.id}"
        post.source_id = source_id
        linked_ids.append(post.id)

        repo.upsert_source(
            db,
            Source(
                id=source_id,
                library_id=library_id,
                platform="instagram",
                content_type=(post.type or "reel").lower(),
                url=post.url,
                author=post.creator_username,
                title=post.title or "",
                description=post.description,
                extracted_text=post.extracted_knowledge,
                status="indexed",
                ingest_status="full_indexed",
                published_at=post.published_at,
                indexed_at=post.indexed_at or time.time(),
            ),
        )
        repo.add_source_to_library(db, library_id, source_id)

        content = post.extracted_knowledge or post.description or ""
        pieces = chunk_text(content)
        if pieces:
            chunk_rows = [
                Chunk(
                    id=f"{source_id}:{ordinal}",
                    source_id=source_id,
                    library_id=library_id,
                    ordinal=ordinal,
                    text=piece,
                    token_count=len(piece.split()),
                )
                for ordinal, piece in enumerate(pieces)
            ]
            repo.replace_chunks(db, source_id, library_id, chunk_rows)

    db.commit()
    LexicalRetriever.invalidate(library_id)
    return linked_ids


def delete_global_posts(post_ids: List[str]) -> int:
    """Permanently delete posts, their linked sources, chunks, and vectors from the global system."""
    if not post_ids:
        return 0

    db = get_session()
    try:
        posts = db.query(repo.Post).filter(repo.Post.id.in_(post_ids)).all()
        if not posts:
            return 0

        post_urls = [p.url for p in posts if p.url]
        direct_pids = [p.id for p in posts]

        # Find all sources representing these posts across all libraries
        from sqlalchemy import or_
        source_filters = [
            repo.Source.id.in_(direct_pids),
            repo.Source.id.in_([f"post:{pid}" for pid in direct_pids]),
        ]
        if post_urls:
            source_filters.append(repo.Source.url.in_(post_urls))
        for pid in direct_pids:
            source_filters.append(repo.Source.id.like(f"%:{pid}"))

        matching_sources = db.query(repo.Source).filter(or_(*source_filters)).all()
        matching_source_ids = list({s.id for s in matching_sources})
        impacted_library_ids = list({s.library_id for s in matching_sources if s.library_id})

        # 1. Delete chunks
        if matching_source_ids:
            db.query(repo.Chunk).filter(repo.Chunk.source_id.in_(matching_source_ids)).delete(synchronize_session=False)

            # SQLite FTS cleanup
            if db.get_bind() and str(db.get_bind().dialect.name) == "sqlite":
                for sid in matching_source_ids:
                    db.execute(
                        text("DELETE FROM chunks_fts WHERE chunk_id LIKE :prefix"),
                        {"prefix": f"{sid}:%"},
                    )

            # 2. Delete library_sources relations
            db.query(repo.LibrarySource).filter(repo.LibrarySource.source_id.in_(matching_source_ids)).delete(synchronize_session=False)

            # 3. Delete sources
            db.query(repo.Source).filter(repo.Source.id.in_(matching_source_ids)).delete(synchronize_session=False)

        # 4. Delete saved posts references
        db.query(repo.UserSavedPost).filter(repo.UserSavedPost.post_id.in_(direct_pids)).delete(synchronize_session=False)

        # 5. Delete posts
        deleted_count = db.query(repo.Post).filter(repo.Post.id.in_(direct_pids)).delete(synchronize_session=False)

        db.commit()

        # Invalidate lexical indexers for impacted libraries
        for lib_id in impacted_library_ids:
            LexicalRetriever.invalidate(lib_id)

        # Clean up Pinecone vectors if configured
        try:
            from src.indexer.pinecone_indexer import PineconeIndexer
            indexer = PineconeIndexer()
            indexer.delete_posts(direct_pids)
            for sid in matching_source_ids:
                indexer.delete_source(sid)
        except Exception as e:
            logger.warning("Pinecone deletion skipped or failed: %s", e)

        return deleted_count
    finally:
        db.close()


