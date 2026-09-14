import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests
from requests.exceptions import ChunkedEncodingError, ConnectionError, HTTPError, Timeout

logger = logging.getLogger(__name__)

DOWNLOAD_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, ChunkedEncodingError, Timeout)):
        return True
    if isinstance(exc, HTTPError) and exc.response is not None:
        return exc.response.status_code in {408, 429, 500, 502, 503, 504}
    return False


class MediaDownloader:
    def __init__(self, download_dir: str = "data/raw"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.setdefault("User-Agent", BROWSER_UA)

    def download_media_items(
        self,
        media_items: List[Dict[str, str]],
        post_id: str,
        permalink: Optional[str] = None,
        progress: Optional[Callable[[str], None]] = None,
    ) -> List[Dict[str, str]]:
        def note(message: str) -> None:
            logger.info(message)
            if progress:
                progress(message)
        def download_one(args):
            idx, item = args
            m_type = item.get("type", "image")
            m_url = item.get("url")
            if not m_url:
                return None

            ext = ".mp4" if m_type == "video" else ".jpg"
            file_path = self.download_dir / f"{post_id}_{idx}{ext}"
            if file_path.exists() and file_path.stat().st_size > 0:
                return {"type": m_type, "path": str(file_path.resolve())}

            last_error = None
            for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
                try:
                    self._download_to_file(m_url, file_path)
                    return {"type": m_type, "path": str(file_path.resolve())}
                except Exception as e:
                    last_error = e
                    self._unlink(file_path)
                    if attempt < DOWNLOAD_ATTEMPTS and _retryable(e):
                        wait = RETRY_BACKOFF_SECONDS * attempt
                        note(
                            f"CDN dropped ({attempt}/{DOWNLOAD_ATTEMPTS}), retry in {wait:.0f}s"
                        )
                        time.sleep(wait)
                        continue
                    note(f"CDN download failed: {e}")
                    return None
            note(f"CDN download failed: {last_error}")
            return None

        max_workers = min(4, max(1, len(media_items))) if media_items else 1
        results: List[Dict[str, str]] = []
        if media_items:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                results = [item for item in executor.map(download_one, enumerate(media_items)) if item]

        wanted_video = any(item.get("type") == "video" for item in media_items)
        got_video = any(item.get("type") == "video" for item in results)
        needs_fallback = bool(permalink) and (not results or (wanted_video and not got_video))
        if not needs_fallback:
            return results

        note("CDN failed, downloading with yt-dlp...")
        fallback = self._ytdlp_fallback(permalink, post_id)
        if not fallback:
            note("yt-dlp fallback failed")
            return results
        if wanted_video and not got_video:
            return [item for item in results if item.get("type") != "video"] + fallback
        return fallback

    def _download_to_file(self, url: str, file_path: Path) -> None:
        response = self.session.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(file_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)
        if not file_path.exists() or file_path.stat().st_size == 0:
            raise ConnectionError("Downloaded file was empty")

    def _ytdlp_fallback(self, permalink: str, post_id: str) -> List[Dict[str, str]]:
        try:
            from src.pipeline._common import download_with_ytdlp

            return download_with_ytdlp(permalink, post_id, prefix="ig") or []
        except Exception as exc:
            logger.warning("yt-dlp fallback failed for %s: %s", permalink, exc)
            return []

    @staticmethod
    def _unlink(path: Path) -> None:
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    def cleanup_items(self, items: List[Dict[str, str]]) -> None:
        for item in items:
            p = Path(item["path"])
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

    def close(self) -> None:
        self.session.close()
