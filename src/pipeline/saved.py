import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.saved import parse_saved_posts
from src.analyzer.gemini_analyzer import GeminiAnalyzer
from src.indexer.pinecone_indexer import PineconeIndexer
from src.pipeline._common import Progress, download_with_ytdlp, echo
from storage.db import get_session
import storage.repositories as repo


def import_user_saved_posts(user_id: str = "default", file_path: Path = None) -> Dict[str, Any]:
    if not file_path or not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    source = str(file_path)
    if file_path.suffix.lower() == ".zip":
        from config.saved import _extract_saved_posts_json_from_zip
        raw = _extract_saved_posts_json_from_zip(file_path)
        source = f"{file_path.name} -> your_instagram_activity/saved/saved_posts.json"
    else:
        raw = file_path.read_bytes()

    data = json.loads(raw.decode("utf-8"))
    items = parse_saved_posts(data)

    db = get_session()
    new_saved_count = 0
    try:
        for item in items:
            post_id = item["id"]
            existing_post = repo.get_post(db, post_id)
            if not existing_post:
                from storage.models import Post
                db.add(
                    Post(
                        id=post_id,
                        url=item["url"],
                        creator_username="",
                        type="Reel" if "/reel/" in item["url"] else "Post",
                        description=(item.get("title", "") + "\n" + item.get("caption", "")).strip(),
                    )
                )
                db.commit()

            if repo.add_user_saved_post(db, user_id, post_id, source_url=item["url"]):
                new_saved_count += 1

        state = repo.get_user_saved_state(db, user_id)
        state.total = repo.count_user_saved_posts(db, user_id)
        state.imported_at = datetime.now(timezone.utc).isoformat()
        state.source = source
        repo.save_user_saved_state(db, state)
    finally:
        db.close()

    return {"total": len(items), "new_saved": new_saved_count, "source": source}


def process_saved(
    user_id: str = "default",
    *,
    limit: Optional[int] = None,
    caption_only: bool = False,
    workers: int = 4,
    progress: Progress = echo,
) -> Dict[str, Any]:
    db = get_session()
    try:
        user_saved_post_ids = repo.get_user_saved_post_ids(db, user_id)
        saved_posts = [repo.get_post(db, pid) for pid in user_saved_post_ids]
        saved_posts = [p for p in saved_posts if p is not None]
    finally:
        db.close()

    if not saved_posts:
        raise ValueError("No saved posts imported for this user. Run 'saved import' first.")

    pending = [p for p in saved_posts if not p.indexed_at or not p.extracted_knowledge]
    already_indexed = len(saved_posts) - len(pending)

    progress(f"User saved posts: {len(saved_posts)} total | Already indexed: {already_indexed} | Pending extraction: {len(pending)}")

    if limit is not None:
        pending = pending[:limit]

    if not pending:
        return {"processed": 0, "already_indexed": already_indexed, "failed": 0}

    analyzer = GeminiAnalyzer()
    indexer = PineconeIndexer()

    def process_item(position: int, post) -> Tuple[str, str, Optional[Exception]]:
        pid = post.id
        description = post.description or ""
        media_files = []
        try:
            if not caption_only and post.url:
                progress(f"[{position}/{len(pending)}] Downloading saved post {pid}")
                try:
                    media_files = download_with_ytdlp(post.url, pid) or []
                except Exception as e:
                    progress(f"yt-dlp failed for {pid}: {e}")

            if media_files:
                progress(f"[{position}/{len(pending)}] Analyzing saved post {pid}")
                extracted_text = analyzer.extract_knowledge(media_files, description)
            else:
                if not description:
                    return "skipped", pid, None
                progress(f"[{position}/{len(pending)}] Analyzing saved post {pid}")
                extracted_text = analyzer.extract_knowledge([], description)

            indexer.index_post(
                post_id=pid,
                url=post.url,
                creator_username=post.creator_username or "saved",
                post_type=post.type or "Post",
                description=description,
                extracted_text=extracted_text,
            )
            return "ok", pid, None
        except Exception as e:
            return "failed", pid, e
        finally:
            for mf in media_files:
                if os.path.exists(mf["path"]):
                    os.remove(mf["path"])

    processed = 0
    failed = 0
    skipped = 0

    progress(f"Processing {len(pending)} posts with {workers} workers...")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_item, position, post): post
            for position, post in enumerate(pending, 1)
        }
        for future in as_completed(futures):
            status, pid, error = future.result()
            if status == "ok":
                processed += 1
                progress(f"  ✓ Processed and indexed {pid}")
            elif status == "skipped":
                skipped += 1
                progress(f"  - Skipped {pid} (no media/caption)")
            else:
                failed += 1
                progress(f"  ✗ Failed {pid}: {error}")

    return {
        "processed": processed,
        "already_indexed": already_indexed,
        "skipped": skipped,
        "failed": failed,
    }

