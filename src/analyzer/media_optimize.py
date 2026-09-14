"""Shrink media before Gemini upload so extraction stays readable but cheaper."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MAX_HEIGHT = 720
SKIP_UNDER_BYTES = 8 * 1024 * 1024


def video_optimize_enabled() -> bool:
    return os.getenv("GEMINI_VIDEO_OPTIMIZE", "true").strip().lower() in {"1", "true", "yes", "on"}


def max_video_height() -> int:
    try:
        return max(360, int(os.getenv("GEMINI_VIDEO_MAX_HEIGHT", str(DEFAULT_MAX_HEIGHT))))
    except ValueError:
        return DEFAULT_MAX_HEIGHT


def ytdlp_format() -> str:
    height = max_video_height()
    return f"bv*[height<={height}]+ba/b[height<={height}]/best"


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def probe_video(path: str) -> Tuple[Optional[int], Optional[int]]:
    """Return (height, size_bytes). Height is None if ffprobe is unavailable."""
    size = Path(path).stat().st_size if Path(path).exists() else None
    if not shutil.which("ffprobe"):
        return None, size
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "csv=p=0",
            path,
        ],
        timeout=20,
    )
    if result.returncode != 0:
        return None, size
    raw = (result.stdout or "").strip().splitlines()
    try:
        height = int(raw[0]) if raw else None
    except ValueError:
        height = None
    return height, size


def should_transcode(path: str) -> bool:
    if not video_optimize_enabled():
        return False
    if not shutil.which("ffmpeg"):
        logger.info("ffmpeg not on PATH; uploading original video")
        return False
    height, size = probe_video(path)
    max_h = max_video_height()
    if height is not None and height <= max_h and (size or 0) <= SKIP_UNDER_BYTES:
        return False
    if height is not None and height <= max_h:
        # Already 720p or lower, but heavy bitrate — still worth a light re-encode.
        return (size or 0) > SKIP_UNDER_BYTES
    if height is None:
        return (size or 0) > SKIP_UNDER_BYTES
    return True


def transcode_video(path: str) -> Optional[str]:
    src = Path(path)
    dest = src.with_name(f"{src.stem}_gemini.mp4")
    height = max_video_height()
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vf",
        f"scale=-2:'min({height},ih)'",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-r",
        "24",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    result = _run(cmd, timeout=180)
    if result.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        logger.warning("Video transcode failed for %s: %s", path, (result.stderr or "")[-400:])
        if dest.exists():
            dest.unlink(missing_ok=True)
        return None
    logger.info(
        "Transcoded %s -> %s (%s bytes -> %s bytes)",
        src.name,
        dest.name,
        src.stat().st_size,
        dest.stat().st_size,
    )
    return str(dest.resolve())


def prepare_for_gemini(item: Dict[str, str]) -> Dict[str, str]:
    """Return a media item dict, possibly pointing at a smaller temp video."""
    if item.get("type") != "video":
        return item
    path = item.get("path")
    if not path or not Path(path).exists():
        return item
    if not should_transcode(path):
        return item
    optimized = transcode_video(path)
    if not optimized:
        return item
    return {**item, "path": optimized, "optimized": "1"}
