import glob
import logging
import os
import uuid
from typing import Dict, List, Optional
from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)


class WhisperAnalyzer:
    def __init__(self, mode: str = "local_whisper", download_dir: str = "data/raw"):
        if mode not in {"local_whisper", "openai_whisper"}:
            raise ValueError("mode must be 'local_whisper' or 'openai_whisper'")
        self.mode = mode
        self.download_dir = download_dir
        if self.mode == "local_whisper":
            try:
                from faster_whisper import WhisperModel
                self.model = WhisperModel("small", device="cpu", compute_type="int8")
            except Exception as e:
                raise ImportError("faster-whisper is required for local_whisper mode") from e
        else:
            try:
                import openai
                self.openai = openai
            except Exception as e:
                raise ImportError("openai library is required for openai_whisper mode") from e


    def _download_audio(self, source_url: str) -> str:
        """Download audio-only with yt-dlp into the download dir. Returns the local file path."""
        os.makedirs(self.download_dir, exist_ok=True)
        base = os.path.join(self.download_dir, f"audio_{uuid.uuid4().hex}")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": base + ".%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "retries": 3,
            "concurrent_fragment_downloads": 4,
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source_url, download=True)
            filename = ydl.prepare_filename(info)
        if os.path.exists(filename):
            return filename
        candidates = glob.glob(base + ".*")
        if candidates:
            return candidates[0]
        raise RuntimeError(f"yt-dlp produced no file for {source_url}")

    def _transcribe(self, file_path: str) -> str:
        """Transcribe an audio/video file (faster-whisper and OpenAI both decode mp4/m4a directly)."""
        if self.mode == "local_whisper":
            segments, _ = self.model.transcribe(file_path, beam_size=5)
            return " ".join(seg.text for seg in segments)
        with open(file_path, "rb") as f:
            response = self.openai.audio.transcriptions.create(model="whisper-1", file=f)
        return response.text

    def extract_knowledge(
        self,
        media_files: List[Dict[str, str]],
        post_description: str,
        video_urls: Optional[List[str]] = None,
    ) -> str:
        """Extract knowledge from audio tracks.

        ``video_urls`` (preferred) is a list of URLs to fetch audio from with yt-dlp.
        If not provided, ``media_files`` entries with ``type == 'video'`` are used
        as local file paths. If no audio is available, the caption is returned
        unchanged.
        """
        if video_urls is not None:
            sources = list(video_urls)
        else:
            sources = [m["path"] for m in media_files if m.get("type") == "video"]

        transcriptions: List[str] = []
        last_error: Optional[Exception] = None
        for source in sources:
            local_path = source
            try:
                if str(source).startswith("http"):
                    local_path = self._download_audio(source)
                txt = self._transcribe(local_path)
                transcriptions.append(txt)
                logger.info("Transcribed %s", source)
            except Exception as e:
                last_error = e
                logger.error("ERROR transcribing %s: %s", source, e)
            finally:
                if local_path != source and os.path.exists(local_path):
                    os.remove(local_path)

        if transcriptions:
            combined = "\n".join(transcriptions)
            desc_part = f"\n\n**Post Description**\n{post_description}" if post_description else ""
            return f"**Transcribed Audio**\n\n{combined}{desc_part}\n"
        if last_error is not None:
            raise last_error
        return post_description