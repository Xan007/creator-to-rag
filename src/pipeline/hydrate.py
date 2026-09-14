"""Upgrade caption-only sources to full media extraction."""

import logging
import os
from typing import Any, Dict, List, Optional

from src.analyzer.caption_triage import CAPTION_INDEXED, FULL_INDEXED, HYDRATING
from src.pipeline._common import Progress, download_with_ytdlp, echo
from storage.db import get_session
import storage.repositories as repo

logger = logging.getLogger(__name__)


def source_ids_from_matches(matches: List[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    seen = set()
    for match in matches:
        meta = match.get("metadata") or {}
        sid = meta.get("source_id") or meta.get("post_id")
        if sid and sid not in seen:
            seen.add(sid)
            ids.append(sid)
    return ids


def caption_indexed_ids_from_matches(
    matches: List[Dict[str, Any]],
    *,
    library_id: Optional[str] = None,
) -> List[str]:
    """Prefer SQL ingest_status; fall back to Pinecone metadata."""
    candidate_ids = source_ids_from_matches(matches)
    if not candidate_ids:
        return []
    db = get_session()
    try:
        rows = repo.list_sources_by_ids(db, candidate_ids)
        by_id = {row.id: row for row in rows}
        extra = []
        if library_id:
            for sid in candidate_ids:
                if sid in by_id:
                    continue
                composed = f"{library_id}:{sid}"
                extra.append(composed)
            if extra:
                for row in repo.list_sources_by_ids(db, extra):
                    by_id[row.id] = row
                    post_id = row.id.split(":", 1)[-1]
                    by_id.setdefault(post_id, row)
        needed = []
        seen = set()
        for sid in candidate_ids:
            row = by_id.get(sid)
            if row is None and library_id:
                row = by_id.get(f"{library_id}:{sid}")
            if row is not None:
                if row.ingest_status == CAPTION_INDEXED and row.id not in seen:
                    seen.add(row.id)
                    needed.append(row.id)
                continue
            meta_status = None
            for match in matches:
                meta = match.get("metadata") or {}
                if meta.get("source_id") == sid or meta.get("post_id") == sid:
                    meta_status = meta.get("ingest_status")
                    break
            if meta_status == CAPTION_INDEXED and sid not in seen:
                seen.add(sid)
                needed.append(sid)
        return needed
    finally:
        db.close()


def overlay_hydrated_knowledge(
    matches: List[Dict[str, Any]],
    hydrated: Dict[str, str],
) -> List[Dict[str, Any]]:
    if not hydrated:
        return matches
    updated = []
    for match in matches:
        cloned = dict(match)
        meta = dict(cloned.get("metadata") or {})
        sid = meta.get("source_id") or meta.get("post_id")
        text = None
        if sid in hydrated:
            text = hydrated[sid]
        else:
            for key, value in hydrated.items():
                if sid and (key.endswith(f":{sid}") or sid.endswith(f":{key}")):
                    text = value
                    break
        if text:
            meta["extracted_knowledge"] = text
            meta["ingest_status"] = FULL_INDEXED
            cloned["metadata"] = meta
        updated.append(cloned)
    return updated


def _lookup_source(source_id: str, library_id: Optional[str]):
    db = get_session()
    try:
        source = repo.get_source(db, source_id)
        if source:
            return source
        if library_id:
            source = repo.get_source(db, f"{library_id}:{source_id}")
            if source:
                return source
        post = repo.get_post(db, source_id)
        if post and post.source_id:
            source = repo.get_source(db, post.source_id)
            if source:
                return source
        return None
    finally:
        db.close()


def _mark_ingest_status(source_id: str, status: str) -> None:
    db = get_session()
    try:
        source = repo.get_source(db, source_id)
        if source:
            source.ingest_status = status
            db.commit()
    finally:
        db.close()


def _hydrate_one(source, progress: Progress) -> str:
    from src.analyzer.gemini_analyzer import GeminiAnalyzer
    from src.indexer.pinecone_indexer import PineconeIndexer

    url = source.url
    if not url:
        raise ValueError(f"Source {source.id} has no URL to hydrate.")
    _mark_ingest_status(source.id, HYDRATING)
    progress(f"Hydrating caption-only source {source.id}")
    files = download_with_ytdlp(url, source.id.replace(":", "_"), prefix="hydrate") or []
    try:
        analyzer = GeminiAnalyzer()
        extracted = analyzer.extract_knowledge(
            files, source.description or "", progress=progress
        )
        indexer = PineconeIndexer()
        post = None
        db = get_session()
        try:
            if source.id.count(":") >= 1:
                post_id = source.id.split(":", 1)[1]
                post = repo.get_post(db, post_id)
            if post is None and source.url:
                # Instagram shortcode posts keyed by post id.
                maybe = source.id.split(":")[-1]
                post = repo.get_post(db, maybe)
        finally:
            db.close()

        if post is not None:
            indexer.index_post(
                post_id=post.id,
                url=url,
                creator_username=post.creator_username or source.author or "",
                post_type=post.type or "Post",
                description=source.description or post.description or "",
                extracted_text=extracted,
                library_id=source.library_id,
                ingest_status=FULL_INDEXED,
            )
        else:
            indexer.index_source(
                source_id=source.id,
                library_id=source.library_id,
                url=url,
                platform=source.platform or "url",
                author=source.author or "",
                title=source.title or "",
                description=source.description or "",
                extracted_text=extracted,
                ingest_status=FULL_INDEXED,
            )
        return extracted
    except Exception:
        _mark_ingest_status(source.id, CAPTION_INDEXED)
        raise
    finally:
        if files and not os.getenv("CRAG_KEEP_HYDRATE_MEDIA"):
            from src.downloader.media_downloader import MediaDownloader
            MediaDownloader().cleanup_items(files)


def hydrate_sources(
    source_ids: List[str],
    library_id: Optional[str] = None,
    progress: Progress = echo,
) -> Dict[str, str]:
    """Download and full-index caption-only sources. Failures are skipped."""
    hydrated: Dict[str, str] = {}
    for source_id in source_ids:
        source = _lookup_source(source_id, library_id)
        if source is None:
            progress(f"Skip hydrate {source_id}: source not found")
            continue
        if source.ingest_status == FULL_INDEXED:
            continue
        try:
            extracted = _hydrate_one(source, progress)
            hydrated[source.id] = extracted
            if source_id != source.id:
                hydrated[source_id] = extracted
        except Exception as exc:
            logger.warning("Hydrate failed for %s: %s", source_id, exc)
            progress(f"Hydrate failed for {source_id}: {exc}")
    return hydrated
