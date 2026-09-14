import logging
import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional
from google import genai
from config.env import load_runtime_env
from src.analyzer.media_optimize import prepare_for_gemini, should_transcode
from src.llm.gemini_limits import GEMINI_REQUEST_LIMIT

load_runtime_env()

logger = logging.getLogger(__name__)

DEFAULT_EXTRACTION_MODEL = "gemini-3.5-flash"
# Each Flash SKU has its own free-tier RPM/RPD/TPM. Skip Gemma (no native
# video+audio on the hosted API) and Pro 3.1 (paid-only).
DEFAULT_EXTRACTION_FALLBACKS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


def extraction_models() -> List[str]:
    primary = os.getenv("GEMINI_EXTRACTION_MODEL", DEFAULT_EXTRACTION_MODEL).strip()
    primary = primary or DEFAULT_EXTRACTION_MODEL
    extra = [
        value.strip()
        for value in os.getenv("GEMINI_EXTRACTION_FALLBACK_MODELS", "").split(",")
        if value.strip()
    ]
    fallback = [*extra, *DEFAULT_EXTRACTION_FALLBACKS]
    # Migrate the model used by older local .env files automatically. Gemini
    # rejects this model for new accounts instead of returning a normal 404.
    if primary in {"gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"}:
        fallback.append(DEFAULT_EXTRACTION_MODEL)
    return list(dict.fromkeys([primary, *fallback]))

EXTRACTION_PROMPT_TEMPLATE = """
You are an expert knowledge extractor building a permanent AI knowledge base from creator content.
Analyze the provided media (video with audio, images, or slides) together with the post's caption.

Original Caption:
"{post_description}"

Task:
Extract ALL dense, factual, actionable knowledge shown OR spoken in the media, plus anything valuable from the caption.

Hard rules:
1. Copy every number EXACTLY as stated: reps x sets (e.g. 12x3), seconds, grams, ml, calories, temps, times. Never round, convert, or invent numbers.
2. Transcribe the key points of the SPOKEN audio (steps, tips, warnings, corrections) - not filler.
3. Read and include relevant ON-SCREEN text: overlays, lists, whiteboards, ingredient labels, exercise names.
4. Write the output in the SAME language as the original caption.
5. If the media adds nothing beyond the caption, say so explicitly on a "Notes:" line and extract only from the caption.
6. No greetings, no conclusions, no fluff, no opinions of your own. Facts and instructions only.

Output format (markdown, use these exact section headers; omit a section only if truly empty):

## Topic
(one line: what this post teaches)

## Steps / Method
(numbered steps or exercise list with exact sets/reps/durations/quantities)

## Key Numbers
(bullet list of every measurement, amount, dosage or timing mentioned)

## On-Screen Text
(text visible in frames/slides that is not already covered above)

## Spoken Key Points
(the most important things said in the audio)

## Notes
(equipment needed, common mistakes warned about, who it's for, or 'media adds nothing beyond caption')
"""


def build_extraction_prompt(post_description: str) -> str:
    return EXTRACTION_PROMPT_TEMPLATE.format(post_description=post_description.strip())


class GeminiAnalyzer:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")
        self.client = genai.Client(api_key=key)

    def extract_knowledge(
        self,
        media_files: List[Dict[str, str]],
        post_description: str,
        progress: Optional[Callable[[str], None]] = None,
    ) -> str:
        def note(message: str) -> None:
            logger.info(message)
            if progress:
                progress(message)

        uploaded_files = []
        local_temps = []
        try:
            if not media_files:
                note("no media file — extracting from caption")
            for item in media_files:
                kind = item.get("type", "file")
                path = item.get("path") or ""
                if kind == "video" and path and should_transcode(path):
                    note("shrinking video to 720p...")
                prepared = prepare_for_gemini(item)
                path = prepared["path"]
                if prepared.get("optimized"):
                    local_temps.append(path)
                size_mb = Path(path).stat().st_size / (1024 * 1024) if Path(path).exists() else 0
                note(f"uploading {kind} to Gemini ({size_mb:.1f} MB)...")
                gfile = self.client.files.upload(file=path)

                if prepared.get("type") == "video":
                    started = time.time()
                    last_report = -10
                    while gfile.state.name == "PROCESSING":
                        elapsed = int(time.time() - started)
                        if elapsed - last_report >= 10:
                            note(f"Gemini processing video... {elapsed}s (this can take a minute)")
                            last_report = elapsed
                        time.sleep(2)
                        gfile = self.client.files.get(name=gfile.name)

                    elapsed = int(time.time() - started)
                    if gfile.state.name == "FAILED":
                        note(f"Gemini failed to process video after {elapsed}s")
                        continue
                    note(f"video ready after {elapsed}s")

                uploaded_files.append(gfile)

            prompt = build_extraction_prompt(post_description)
            contents = uploaded_files + [prompt] if uploaded_files else [prompt]

            last_error = None
            for model_name in extraction_models():
                for attempt in range(4):
                    try:
                        chat = self.client.chats.create(model=model_name)
                        if not GEMINI_REQUEST_LIMIT.acquire(blocking=False):
                            note(f"waiting for Gemini slot ({model_name}, 1 extract at a time)...")
                            GEMINI_REQUEST_LIMIT.acquire()
                        try:
                            note(f"extracting with {model_name}...")
                            response = chat.send_message(contents)
                        finally:
                            GEMINI_REQUEST_LIMIT.release()
                        return response.text.strip()
                    except Exception as e:
                        last_error = e
                        err_str = str(e)
                        if "503" in err_str or "UNAVAILABLE" in err_str:
                            note(f"{model_name} unavailable, trying next model")
                            break
                        if "404" in err_str or "NOT_FOUND" in err_str:
                            note(f"{model_name} not found, trying next model")
                            break
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            if attempt < 3:
                                wait_seconds = min(30, 5 * (2 ** attempt))
                                note(
                                    f"rate limit on {model_name}, retry {attempt + 1}/4 in {wait_seconds}s"
                                )
                                time.sleep(wait_seconds)
                            else:
                                note(f"rate limit persists on {model_name}, trying next model")
                                break
                        else:
                            # Authentication, invalid model, and malformed requests are
                            # deterministic failures; retrying them only adds latency.
                            note(f"{model_name} failed: {e}")
                            break

            raise RuntimeError(f"All fallback models failed for knowledge extraction: {last_error}")

        finally:
            for temp_path in local_temps:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass
            for gfile in uploaded_files:
                try:
                    self.client.files.delete(name=gfile.name)
                except Exception:
                    pass

