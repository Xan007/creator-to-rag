"""Low-cost Apify social connectors.

Actor IDs are configurable because Store actors can change. The defaults are
the cheap, high-volume actors selected for the MVP:
- TikTok: clockworks/full-tiktok-api-scraper
"""

import os
from typing import Any, Dict, Iterable, List, Optional

from apify_client import ApifyClient

from src.connectors.models import NormalizedSource


TIKTOK_ACTOR = os.getenv("APIFY_TIKTOK_ACTOR", "clockworks/full-tiktok-api-scraper")


def _items(client: ApifyClient, actor_id: str, run_input: Dict[str, Any], limit: int) -> Iterable[Dict[str, Any]]:
    if limit < 1:
        return []
    from src.scraper.apify_cache import load_cache, save_cache

    cache_payload = {"actor": actor_id, "input": run_input, "limit": limit}
    cached = load_cache("tiktok", cache_payload, min_count=1)
    if isinstance(cached, list):
        return cached[:limit]

    run = client.actor(actor_id).call(
        run_input=run_input,
        max_total_charge_usd=float(os.getenv("APIFY_MAX_TOTAL_CHARGE_USD", "1.00")),
    )
    dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id
    items: List[Dict[str, Any]] = []
    for item in client.dataset(dataset_id).iterate_items():
        items.append(item)
        if len(items) >= limit:
            break
    save_cache("tiktok", cache_payload, items)
    return items


def _normalize(item: Dict[str, Any], platform: str) -> Optional[NormalizedSource]:
    url = item.get("url") or item.get("webVideoUrl") or item.get("videoUrl") or item.get("inputUrl")
    if not url:
        return None
    author = (
        item.get("authorMeta", {}).get("name")
        if isinstance(item.get("authorMeta"), dict)
        else item.get("channelName") or item.get("channelTitle")
    ) or item.get("author") or item.get("ownerUsername") or ""
    title = item.get("title") or item.get("text") or item.get("desc") or ""
    description = "\n".join(filter(None, [title, item.get("description"), item.get("caption")]))
    return NormalizedSource(
        url=url,
        platform=platform,
        content_type="video",
        author=author,
        title=title,
        description=description,
        external_id=str(item.get("id") or item.get("videoId") or ""),
    )


class ApifySocialConnector:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("APIFY_API_KEY")
        if not key:
            raise ValueError("APIFY_API_KEY environment variable is not set.")
        self.client = ApifyClient(key)

    def tiktok(self, urls: List[str], limit: int = 20) -> List[NormalizedSource]:
        data = {"startUrls": [{"url": u} for u in urls], "maxItems": limit}
        return [s for item in _items(self.client, TIKTOK_ACTOR, data, limit)
                if (s := _normalize(item, "tiktok"))]
