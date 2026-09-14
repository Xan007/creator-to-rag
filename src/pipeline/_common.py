"""Shared types and utilities for pipeline modules."""
import glob
import os
import threading
from typing import Dict, List, Optional, Protocol

from config.paths import RAW_DIR


class Progress(Protocol):
    """Protocol for progress reporting callbacks."""
    def __call__(self, message: str) -> None: ...


def echo(message: str) -> None:
    print(message)


def locked_progress(progress: Progress) -> Progress:
    """Serialize progress lines so concurrent workers don't interleave mid-print."""
    lock = threading.Lock()

    def emit(message: str) -> None:
        with lock:
            progress(message)

    return emit


def post_step(position: int, total: int, post_id: str, message: str) -> str:
    return f"  [{position}/{total} {post_id}] {message}"


def download_with_ytdlp(url: str, pid: str, prefix: str = "saved") -> Optional[List[Dict[str, str]]]:
    """Download a reel/post with yt-dlp (video+audio merged via ffmpeg). Raises on failure."""
    from yt_dlp import YoutubeDL
    from src.analyzer.media_optimize import ytdlp_format

    os.makedirs(RAW_DIR, exist_ok=True)
    outtmpl = os.path.join(RAW_DIR, f"{prefix}_{pid}.%(ext)s")
    ydl_opts = {
        "format": ytdlp_format(),
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "retries": 3,
        "concurrent_fragment_downloads": 4,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
    if os.path.exists(filename):
        return [{"type": "video", "path": filename}]
    candidates = glob.glob(outtmpl.replace("%(ext)s", ".*"))
    return [{"type": "video", "path": candidates[0]}] if candidates else None
