import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.ig_profiles import IGProfileInfo, load_ig_profile, save_ig_profile
from src.pipeline._common import Progress, echo, locked_progress, post_step


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def scrape_profile(
    username: str,
    *,
    newer_than: Optional[str] = None,
    max_posts: int = 200,
    analysis_mode: str = "gemini",
    library_id: Optional[str] = None,
    keep_media: bool = False,
    interests: Optional[str] = None,
    caption_only: bool = False,
    full_media: bool = False,
    progress: Progress = echo,
) -> Dict[str, Any]:
    from src.scraper.apify_scraper import ApifyScraper
    from src.downloader.media_downloader import MediaDownloader
    from src.analyzer.gemini_analyzer import GeminiAnalyzer
    from src.indexer.pinecone_indexer import PineconeIndexer
    from storage.db import get_session
    import storage.repositories as repo

    progress = locked_progress(progress)
    run_start = time.time()
    run_iso = _now_iso()

    profile = load_ig_profile(username)
    if not profile:
        profile = IGProfileInfo(username=username)

    progress(f"Scraping @{username} — {run_iso[:19]}Z")
    progress(
        f"  Mode: {analysis_mode} | Max posts: {max_posts}"
        + (f" | newer than: {newer_than}" if newer_than else "")
        + (" | full media" if full_media else " | caption-first")
    )
    if profile.last_scraped_at:
        dt = datetime.fromtimestamp(profile.last_scraped_at, tz=timezone.utc)
        progress(f"  Last scraped: {dt.isoformat()[:19]}Z")

    db = get_session()
    try:
        known_ids = set(repo.get_all_post_ids(db, creator_username=username))
        if full_media and library_id:
            known_ids -= set(repo.list_caption_indexed_post_ids(db, library_id, username))
    finally:
        db.close()

    progress(f"  Already indexed: {len(known_ids)} post(s) — will skip these.")

    profile.last_run_at = run_iso
    save_ig_profile(profile)

    try:
        scraper = ApifyScraper(only_posts_newer_than=newer_than)
        downloader = MediaDownloader()
        is_whisper = analysis_mode in ("local_whisper", "openai_whisper")
        if is_whisper:
            from src.analyzer.whisper_analyzer import WhisperAnalyzer
            analyzer = WhisperAnalyzer(mode=analysis_mode)
        else:
            analyzer = GeminiAnalyzer()
        indexer = PineconeIndexer()
    except ValueError as e:
        raise ValueError(f"Config error: {e}. Check .env for API keys.")

    new_post_ids: List[str] = []
    failed_ids: List[str] = []

    try:
        progress("Fetching post metadata from Apify...")
        all_posts: List[Dict[str, Any]] = list(
            scraper.get_posts_metadata(username, max_posts, list(known_ids))
        )
        progress(f"  Retrieved {len(all_posts)} new candidate(s).")

        if not all_posts:
            profile.last_scraped_at = run_start
            save_ig_profile(profile)
            return {
                "processed": 0,
                "skipped_known": len(known_ids),
                "failed": 0,
                "total_indexed": len(known_ids),
                "last_scraped_at": run_start,
                "message": "No new posts found — profile is up to date.",
            }

        def process_post_task(post_number: int, post: Dict[str, Any]):
            post_id = post["id"]
            post_url = post["url"]
            post_type = post.get("type", "Post")
            description = post.get("description", "")
            media_items = post.get("media_items", [])
            total = len(all_posts)
            started = time.time()

            def step(message: str) -> None:
                progress(post_step(post_number, total, post_id, message))

            downloaded = []
            audio_sources = []
            try:
                from src.analyzer.caption_triage import resolve_ingest_plan

                should_download, ingest_status = resolve_ingest_plan(
                    description=description,
                    caption_only=caption_only,
                    full_media=full_media,
                    platform="instagram",
                )
                if should_download:
                    step(f"downloading {post_type.lower()}...")
                    if is_whisper:
                        video_urls = [m["url"] for m in media_items if m.get("type") == "video"]
                        audio_sources = [post["url"]] if post.get("url") and video_urls else []
                        audio_sources += [u for u in video_urls if u != post.get("url")]
                    else:
                        downloaded = downloader.download_media_items(
                            media_items,
                            post_id,
                            permalink=post_url,
                            progress=step,
                        ) or []
                        if downloaded:
                            step(f"downloaded {len(downloaded)} file(s)")
                        else:
                            step("no media on disk, Gemini will use the caption")
                    if is_whisper:
                        extracted = analyzer.extract_knowledge(
                            downloaded, description, video_urls=audio_sources
                        )
                    else:
                        extracted = analyzer.extract_knowledge(
                            downloaded, description, progress=step
                        )
                else:
                    step("caption-only — skipping download")
                    extracted = description

                indexer.index_post(
                    post_id=post_id,
                    url=post_url,
                    creator_username=username,
                    post_type=post_type,
                    description=description,
                    extracted_text=extracted,
                    library_id=library_id,
                    ingest_status=ingest_status,
                )
                elapsed = time.time() - started
                step(f"indexed in {elapsed:.0f}s")
                return "ok", post_id, None
            except Exception as err:
                step(f"error: {err}")
                return "error", post_id, err
            finally:
                if downloaded and not keep_media:
                    downloader.cleanup_items(downloaded)

        progress(
            f"Processing {len(all_posts)} post(s) with 3 workers "
            "(downloads in parallel, Gemini extract 1 at a time)..."
        )
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(process_post_task, post_number, post): post
                for post_number, post in enumerate(all_posts, 1)
            }
            for future in as_completed(futures):
                status, pid, err = future.result()
                if status == "ok":
                    new_post_ids.append(pid)
                else:
                    failed_ids.append(pid)

    except Exception as e:
        progress(f"Pipeline error: {e}")
        return {
            "processed": len(new_post_ids),
            "skipped_known": len(known_ids),
            "failed": len(failed_ids),
            "total_indexed": len(known_ids) + len(new_post_ids),
            "last_scraped_at": profile.last_scraped_at,
            "error": str(e),
        }

    elapsed = time.time() - run_start
    profile.last_scraped_at = run_start
    db = get_session()
    try:
        profile.total_posts_scraped = repo.count_posts(db, creator_username=username)
    finally:
        db.close()
    save_ig_profile(profile)

    progress(f"Done in {elapsed:.1f}s — indexed {len(new_post_ids)}, failed {len(failed_ids)}.")

    return {
        "processed": len(new_post_ids),
        "skipped_known": len(known_ids),
        "failed": len(failed_ids),
        "total_indexed": len(known_ids) + len(new_post_ids),
        "last_scraped_at": run_start,
    }


run_profile = scrape_profile

