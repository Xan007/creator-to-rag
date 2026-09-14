"""Product-level ingestion into a user's library."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.connectors.url import extract_url_source
from src.pipeline._common import Progress, download_with_ytdlp, echo, locked_progress, post_step
from storage.db import get_session
import storage.repositories as repo


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
                step("caption-only — skipping download")
                extracted = source.description
            chunks = indexer.index_source(
                source_id=sid,
                library_id=library_id,
                url=source.url,
                platform=source.platform,
                author=source.author,
                title=source.title,
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
                    discovered = getattr(connector, platform)([url], limit=20)
                    nested = ingest_urls(
                        library_id,
                        [item.url for item in discovered],
                        owner_id=owner_id,
                        caption_only=caption_only,
                        keep_media=keep_media,
                        full_media=full_media,
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
