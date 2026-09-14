"""Disk cache for Apify actor datasets.

Stores raw/normalized scrape payloads so a re-run of the same profile/URLs
does not pay Apify again. Downstream skip_ids, newerThan, caption-first, and
already-indexed checks still run on the cached items.

Media CDN URLs can expire; caption-first ingest does not need them, and
hydrate downloads from the permalink via yt-dlp.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from config.env import getenv, load_runtime_env
from config.paths import CONFIG_DIR

logger = logging.getLogger(__name__)

load_runtime_env()


def _cache_enabled() -> bool:
    raw = os.getenv("APIFY_CACHE", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _ttl_seconds() -> float:
    hours = float(os.getenv("APIFY_CACHE_TTL_HOURS", "24"))
    return max(hours, 0) * 3600


def cache_dir() -> Path:
    root = Path(getenv("CONFIG_DIR", str(CONFIG_DIR))) / "apify_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def cache_key(kind: str, payload: Dict[str, Any]) -> str:
    blob = json.dumps({"kind": kind, **payload}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


def load_cache(kind: str, payload: Dict[str, Any], *, min_count: int = 0) -> Optional[Any]:
    if not _cache_enabled():
        return None
    path = cache_dir() / f"{kind}_{cache_key(kind, payload)}.json"
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    fetched_at = float(record.get("fetched_at") or 0)
    if fetched_at and (time.time() - fetched_at) > _ttl_seconds():
        logger.info("Apify cache expired: %s", path.name)
        return None
    if int(record.get("count") or 0) < min_count:
        return None
    logger.info("Apify cache hit (%s, %s items)", kind, record.get("count"))
    return record.get("data")


def save_cache(kind: str, payload: Dict[str, Any], data: Any) -> None:
    if not _cache_enabled():
        return
    count = len(data) if isinstance(data, list) else 1
    record = {
        "fetched_at": time.time(),
        "count": count,
        "payload": payload,
        "data": data,
    }
    path = cache_dir() / f"{kind}_{cache_key(kind, payload)}.json"
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    logger.info("Apify cache store (%s, %s items)", kind, count)
