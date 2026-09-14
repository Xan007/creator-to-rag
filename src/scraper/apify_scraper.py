import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional
from apify_client import ApifyClient
from config.env import load_runtime_env

load_runtime_env()

logger = logging.getLogger(__name__)

ACTOR_ID = "sones/instagram-posts-scraper-lowcost"
ACTOR_MAX_POSTS_PER_PROFILE = 500

MEDIA_TYPE_TO_POST_TYPE = {1: "Image", 2: "Video", 8: "Sidecar"}


def _extract_hashtags(text: str) -> List[str]:
    return re.findall(r"#(\w+)", text)


def _best_video_url(node: Dict[str, Any]) -> Optional[str]:
    if node.get("video_url"):
        return node["video_url"]
    versions = [v for v in (node.get("video_versions") or []) if isinstance(v, dict) and v.get("url")]
    if not versions:
        return None
    versions.sort(key=lambda v: v.get("width") or 0, reverse=True)
    return versions[0]["url"]


def _best_image_url(node: Dict[str, Any]) -> Optional[str]:
    if node.get("image_url"):
        return node["image_url"]
    iv = node.get("image_versions2")
    candidates = iv.get("candidates") if isinstance(iv, dict) else None
    usable = [(c.get("width") or 0, c["url"]) for c in (candidates or []) if isinstance(c, dict) and c.get("url")]
    if not usable:
        return None
    fitting = [(w, u) for w, u in usable if 0 < w <= 1080]
    if fitting:
        return max(fitting, key=lambda t: t[0])[1]
    return max(usable, key=lambda t: t[0])[1]


def _media_items_for(node: Dict[str, Any], media_type: int, warn_prefix: str = "") -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    if media_type == 2:
        url = _best_video_url(node)
        if url:
            items.append({"type": "video", "url": url})
        else:
            img = _best_image_url(node)
            if img:
                items.append({"type": "image", "url": img})
                logger.warning("%s: video has no video source, falling back to thumbnail", warn_prefix)
    elif media_type == 8:
        for child in node.get("carousel_media") or []:
            child_type = child.get("media_type", 1)
            if child_type == 2:
                url = _best_video_url(child)
                if url:
                    items.append({"type": "video", "url": url})
                    continue
            img = _best_image_url(child)
            if img:
                items.append({"type": "image", "url": img})
    else:
        img = _best_image_url(node)
        if img:
            items.append({"type": "image", "url": img})
    return items


def parse_newer_than(value: str) -> Optional[float]:
    raw = value.strip()
    if not raw:
        return None
    try:
        num = float(raw)
        return num / 1000.0 if num > 1e12 else num
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        pass
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        raise ValueError(f"Unrecognized date format for newerThan: {value}")


def passes_newer_than(item: Dict[str, Any], cutoff_seconds: Optional[float]) -> bool:
    if cutoff_seconds is None:
        return True
    flag = item.get("is_newer_than_cutoff")
    if flag is not None:
        return bool(flag)
    taken_at = item.get("taken_at")
    if isinstance(taken_at, (int, float)):
        seconds = taken_at / 1000.0 if taken_at > 1e12 else float(taken_at)
        return seconds >= cutoff_seconds
    return True


class ApifyScraper:
    def __init__(self, only_posts_newer_than: Optional[str] = None, verbose: bool = True):
        api_key = os.getenv("APIFY_API_KEY")
        if not api_key:
            raise ValueError("APIFY_API_KEY environment variable is not set. Cannot use Apify.")
        self.client = ApifyClient(api_key)
        self.only_posts_newer_than = only_posts_newer_than
        self.verbose = verbose

    def get_posts_metadata(self, username: str, limit: int, skip_ids: List[str]) -> Generator[Dict[str, Any], None, None]:
        skip_set = set(skip_ids)
        requested = min(limit + len(skip_set), ACTOR_MAX_POSTS_PER_PROFILE)

        run_input: Dict[str, Any] = {
            "usernames": [username],
            "postsPerProfile": requested,
            "proxy": {"useApifyProxy": True},
        }

        if self.only_posts_newer_than:
            run_input["newerThan"] = self.only_posts_newer_than

        logger.info("Calling %s for @%s (requested: %d)", ACTOR_ID, username, requested)

        cache_payload = {
            "username": username.lower(),
            "newer_than": self.only_posts_newer_than or "",
        }
        items = None
        from src.scraper.apify_cache import load_cache, save_cache

        cached = load_cache("ig_profile", cache_payload, min_count=requested)
        if isinstance(cached, list):
            items = cached
        else:
            run = self.client.actor(ACTOR_ID).call(run_input=run_input)
            dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id
            items = list(self.client.dataset(dataset_id).iterate_items())
            save_cache("ig_profile", cache_payload, items)
            if not items:
                summary = self._read_run_summary(run)
                if summary:
                    logger.debug("RUN_SUMMARY: %s", json.dumps(summary, default=str)[:800])

        count = 0
        skipped_processed = 0
        skipped_old = 0
        no_media = 0
        cutoff_seconds = parse_newer_than(self.only_posts_newer_than) if self.only_posts_newer_than else None
        for item in items:
            if count >= limit:
                break

            shortcode = item.get("code") or item.get("id", "")
            if not shortcode:
                continue

            if shortcode in skip_set:
                skipped_processed += 1
                continue

            if not passes_newer_than(item, cutoff_seconds):
                skipped_old += 1
                continue

            media_type = item.get("media_type", 1)
            caption_obj = item.get("caption") or {}
            caption_text = caption_obj.get("text", "") if isinstance(caption_obj, dict) else str(caption_obj)

            media_items = _media_items_for(item, media_type, warn_prefix=shortcode)
            if not media_items:
                no_media += 1

            metadata = {
                "id": shortcode,
                "url": item.get("post_url", f"https://www.instagram.com/p/{shortcode}/"),
                "type": MEDIA_TYPE_TO_POST_TYPE.get(media_type, "Image"),
                "description": caption_text,
                "hashtags": _extract_hashtags(caption_text),
                "media_items": media_items,
            }
            yield metadata
            count += 1

        if self.verbose and skipped_old:
            logger.info("Skipped %d post(s) older than the newerThan boundary.", skipped_old)

        logger.info(
            "Scrape complete: yielded %d new post(s), skipped %d processed, %d older, %d without media.",
            count,
            skipped_processed,
            skipped_old,
            no_media,
        )

    def _read_run_summary(self, run: Any) -> Optional[Dict[str, Any]]:
        try:
            kvs_id = (
                run.get("defaultKeyValueStoreId")
                if isinstance(run, dict)
                else getattr(run, "default_key_value_store_id", None)
            )
            if not kvs_id:
                return None
            return self.client.key_value_store(kvs_id).get_record("RUN_SUMMARY")
        except Exception as e:
            logger.warning("Could not read RUN_SUMMARY: %s", e)
            return None