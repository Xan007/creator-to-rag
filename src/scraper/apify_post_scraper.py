import os
from typing import Any, Dict, List, Optional
from apify_client import ApifyClient
from config.env import load_runtime_env
from config.utils import shortcode_from_url
from src.scraper.apify_scraper import _extract_hashtags

load_runtime_env()

ACTOR_ID = "apify/instagram-scraper"


def _normalize_post(item: Dict[str, Any]) -> Dict[str, Any]:
    shortcode = item.get("shortCode") or shortcode_from_url(item.get("url") or item.get("inputUrl") or "")
    post_type = "Sidecar" if item.get("childPosts") else (item.get("type") or "Image")

    media_items: List[Dict[str, str]] = []
    if item.get("childPosts"):
        for child in item["childPosts"]:
            if child.get("videoUrl"):
                media_items.append({"type": "video", "url": child["videoUrl"]})
            elif child.get("displayUrl"):
                media_items.append({"type": "image", "url": child["displayUrl"]})
    if item.get("videoUrl"):
        media_items.insert(0, {"type": "video", "url": item["videoUrl"]})
    if not media_items:
        if item.get("images"):
            media_items = [{"type": "image", "url": u} for u in item["images"]]
        elif item.get("displayUrl"):
            media_items = [{"type": "image", "url": item["displayUrl"]}]

    description = "\n".join(filter(None, [item.get("caption"), item.get("alt")]))
    return {
        "id": shortcode,
        "url": item.get("url") or f"https://www.instagram.com/p/{shortcode}/",
        "type": post_type,
        "description": description or "",
        "hashtags": _extract_hashtags(description or ""),
        "media_items": media_items,
        "owner_username": item.get("ownerUsername"),
    }


class ApifyPostScraper:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("APIFY_API_KEY")
        if not key:
            raise ValueError("APIFY_API_KEY environment variable is not set. Cannot use Apify.")
        self.client = ApifyClient(key)

    def get_posts_by_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        from src.scraper.apify_cache import load_cache, save_cache

        ordered = list(urls)
        cache_payload = {"urls": sorted(ordered)}
        cached = load_cache("ig_urls", cache_payload, min_count=len(ordered))
        if isinstance(cached, list):
            return cached

        run_input = {
            "resultsType": "posts",
            "directUrls": ordered,
            "resultsLimit": len(ordered),
            "addParentData": False,
        }
        run = self.client.actor(ACTOR_ID).call(run_input=run_input)
        dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id

        posts: List[Dict[str, Any]] = []
        for item in self.client.dataset(dataset_id).iterate_items():
            if item.get("error"):
                continue
            try:
                posts.append(_normalize_post(item))
            except ValueError:
                continue
        save_cache("ig_urls", cache_payload, posts)
        return posts

