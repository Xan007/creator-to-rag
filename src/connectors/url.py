from typing import Any, Dict
from urllib.parse import urlparse

from src.connectors.models import NormalizedSource


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if "instagram.com" in host:
        return "instagram"
    if "youtube.com" in host or host == "youtu.be":
        return "youtube"
    if "tiktok.com" in host:
        return "tiktok"
    return "url"


def extract_url_source(url: str) -> NormalizedSource:
    """Read metadata without requiring a platform-specific scraper."""
    from yt_dlp import YoutubeDL

    if not url or not url.startswith(("http://", "https://")):
        raise ValueError("A public http(s) URL is required.")
    try:
        with YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
            info: Dict[str, Any] = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise ValueError(f"Could not read URL metadata: {exc}") from exc
    platform = detect_platform(url)
    if platform == "youtube":
        raise ValueError("YouTube is not supported. Use Instagram or TikTok sources.")
    return NormalizedSource(
        url=url,
        platform=platform,
        content_type="video" if info.get("duration") is not None else "post",
        author=info.get("uploader") or info.get("channel") or "",
        title=info.get("title") or "",
        description="\n".join(filter(None, [info.get("title"), info.get("description")])),
        external_id=str(info.get("id") or ""),
    )
