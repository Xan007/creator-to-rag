import os
import time
from typing import Any, Dict, List, Optional

from config.settings import load_settings
from config.utils import shortcode_from_url
from src.pipeline._common import Progress, download_with_ytdlp, echo
from storage.db import get_session
import storage.repositories as repo


def _reel_meta_via_ytdlp(url: str) -> Dict[str, Any]:
    from yt_dlp import YoutubeDL

    ydl_opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise ValueError(f"Could not fetch reel metadata: {e}")

    shortcode = info.get("id")
    if not shortcode:
        raise ValueError(f"yt-dlp could not determine the reel id for {url}.")
    description = "\n".join(filter(None, [info.get("title"), info.get("description")]))
    return {"id": shortcode, "url": url, "type": "Reel", "description": description}


def add_reel(
    urls: List[str],
    *,
    creator: Optional[str] = None,
    group_id: Optional[str] = None,
    library_id: Optional[str] = None,
    caption_only: bool = False,
    keep_media: bool = False,
    full_media: bool = False,
    progress: Progress = echo,
) -> Dict[str, Any]:
    from src.downloader.media_downloader import MediaDownloader
    from src.analyzer.gemini_analyzer import GeminiAnalyzer
    from src.analyzer.whisper_analyzer import WhisperAnalyzer
    from src.indexer.pinecone_indexer import PineconeIndexer
    from src.scraper.apify_post_scraper import ApifyPostScraper

    urls = [u.strip() for u in urls if u and u.strip()]
    if not urls:
        raise ValueError("No URLs provided.")

    progress(f"Processing {len(urls)} reel/post URL(s)")
    if creator:
        progress(f"Associated creator: @{creator}")

    settings = load_settings()

    apify_meta: Dict[str, Dict[str, Any]] = {}
    try:
        scraper_api = ApifyPostScraper()
        progress("Fetching metadata via Apify...")
        for post in scraper_api.get_posts_by_urls(urls):
            apify_meta[post["id"]] = post
    except Exception as e:
        progress(f"Apify post scraper unavailable ({e}); using yt-dlp fallback.")

    added: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    analyzer = None
    indexer = None
    downloader = MediaDownloader()

    db = get_session()

    try:
        total_urls = len(urls)
        for position, url in enumerate(urls, 1):
            reel_id = None
            downloaded_files: List[Dict[str, str]] = []
            try:
                shortcode = shortcode_from_url(url)
                meta = apify_meta.get(shortcode)

                if meta is None:
                    meta = _reel_meta_via_ytdlp(url)
                else:
                    meta = dict(meta)
                    meta.setdefault("url", url)

                reel_id = meta["id"]
                description = meta.get("description", "")
                creator_username = creator or meta.get("creator_username", "") or ""

                existing_post = repo.get_post(db, reel_id)
                if existing_post and existing_post.extracted_knowledge and existing_post.indexed_at:
                    source = None
                    if library_id:
                        source = repo.get_source(db, f"{library_id}:{reel_id}")
                    already_full = not source or source.ingest_status != "caption_indexed"
                    if already_full or not full_media:
                        progress(f"Reel {reel_id} is already indexed in knowledge base.")
                        if group_id:
                            repo.add_post_to_group(db, group_id, reel_id)
                            progress(f"Added existing reel {reel_id} to group.")
                        added.append({"id": reel_id, "url": url, "already_indexed": True})
                        continue

                mode = settings.engine
                is_whisper = mode in ("local_whisper", "openai_whisper")
                if analyzer is None:
                    analyzer = WhisperAnalyzer(mode=mode) if is_whisper else GeminiAnalyzer()
                    indexer = PineconeIndexer()

                ingest_status = "full_indexed"
                try:
                    from src.analyzer.caption_triage import resolve_ingest_plan

                    should_download, ingest_status = resolve_ingest_plan(
                        description=description,
                        caption_only=caption_only,
                        full_media=full_media,
                        platform="instagram",
                    )
                    if should_download and meta.get("media_items"):
                        downloaded_files = downloader.download_media_items(meta["media_items"], reel_id) or []
                    if should_download:
                        progress(f"[{position}/{total_urls}] Downloading media for {url}")
                    else:
                        progress(f"[{position}/{total_urls}] Caption-only index for {url}")
                    if should_download and not downloaded_files:
                        downloaded_files = download_with_ytdlp(meta["url"], reel_id, prefix="reel") or []
                except Exception as e:
                    progress(f"Media download failed: {e} - using caption.")
                    ingest_status = "caption_indexed"

                progress(f"[{position}/{total_urls}] Analyzing content for {reel_id}...")
                if downloaded_files:
                    extracted_text = analyzer.extract_knowledge(downloaded_files, description)
                else:
                    extracted_text = analyzer.extract_knowledge([], description) if description else ""

                indexer.index_post(
                    post_id=reel_id,
                    url=url,
                    creator_username=creator_username,
                    post_type=meta.get("type", "Reel"),
                    description=description,
                    extracted_text=extracted_text,
                    library_id=library_id,
                    ingest_status=ingest_status,
                )

                if group_id:
                    repo.add_post_to_group(db, group_id, reel_id)
                    progress(f"Added reel {reel_id} to group.")

                added.append({"id": reel_id, "url": url, "already_indexed": False})
            except Exception as e:
                failed.append({"url": url, "error": str(e)})
                progress(f"Failed {url}: {e}")
            finally:
                if downloaded_files and not keep_media:
                    downloader.cleanup_items(downloaded_files)
    finally:
        db.close()

    return {"added": added, "failed": failed}

