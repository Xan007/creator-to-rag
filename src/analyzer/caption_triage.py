import logging
import os
import re
from typing import Literal, Optional, Tuple

logger = logging.getLogger(__name__)

CAPTION_INDEXED = "caption_indexed"
FULL_INDEXED = "full_indexed"
HYDRATING = "hydrating"
INGEST_FAILED = "failed"

TriageVerdict = Literal["rich", "thin"]

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_HASHTAG_RE = re.compile(r"[#@]\w+")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F6FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)
_GENERIC_PHRASES = (
    "link in bio",
    "links in bio",
    "follow for more",
    "follow me",
    "like and follow",
    "more on my page",
    "full video",
    "watch till the end",
    "no caption",
)


def _stripped_caption(description: str) -> str:
    text = description or ""
    text = _URL_RE.sub(" ", text)
    text = _HASHTAG_RE.sub(" ", text)
    text = _EMOJI_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def heuristic_caption_verdict(description: str) -> Optional[TriageVerdict]:
    """Return a verdict without an LLM, or None if the model should decide."""
    raw = (description or "").strip()
    cleaned = _stripped_caption(raw)
    if len(cleaned) < 24:
        return "thin"
    lowered = cleaned.lower()
    if any(phrase in lowered for phrase in _GENERIC_PHRASES) and len(cleaned) < 80:
        return "thin"
    if len(cleaned) >= 140:
        return "rich"
    return None


def _llm_caption_verdict(description: str) -> TriageVerdict:
    from src.llm.factory import LLMClientFactory

    # Same provider/model as answers (Groq when RAG_PROVIDER=groq). Gemini stays
    # on video/multimodal extraction only.
    model = os.getenv("CAPTION_TRIAGE_MODEL") or os.getenv("RAG_MODEL")
    prompt = (
        "Classify this social-media caption for knowledge indexing.\n"
        "RICH = it states what the video teaches with concrete facts "
        "(exercises, sets/reps, ingredients, steps, dosages, technique).\n"
        "THIN = generic promo, jokes, or it does not say what happens in the video.\n"
        "Reply with only RICH or THIN.\n\n"
        f"Caption:\n{description.strip()[:1500]}"
    )
    client = LLMClientFactory.get_client(stage="rag")
    raw = client.generate(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        temperature=0.0,
    )
    token = (raw or "").strip().upper()
    if token.startswith("RICH"):
        return "rich"
    return "thin"


def triage_caption(description: str, platform: str = "") -> TriageVerdict:
    """Decide whether a caption is enough to index without downloading media."""
    del platform  # reserved for future platform-specific rules
    heuristic = heuristic_caption_verdict(description)
    if heuristic is not None:
        return heuristic
    try:
        return _llm_caption_verdict(description)
    except Exception as exc:
        logger.info("Caption triage LLM failed (%s); treating as thin.", exc)
        return "thin"


def resolve_ingest_plan(
    *,
    description: str,
    caption_only: bool = False,
    full_media: bool = False,
    platform: str = "",
) -> Tuple[bool, str]:
    """Return (should_download, ingest_status). `--full` wins over `--caption-only`."""
    if full_media:
        return True, FULL_INDEXED
    if caption_only:
        return False, CAPTION_INDEXED
    if triage_caption(description, platform=platform) == "rich":
        return False, CAPTION_INDEXED
    return True, FULL_INDEXED
