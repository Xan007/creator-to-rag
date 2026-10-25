"""Post title extractor / generator.

Strategy (in order, no extra LLM call if possible):
1. Parse ``## Topic`` from ``extracted_knowledge`` — already generated during
   the main Gemini extraction call, zero extra cost.
2. If ``extracted_knowledge`` has no ``## Topic`` section (e.g. caption-only
   mode), fall back to a small LLM call using the configured client.
3. Last resort: first non-empty line of the caption.

Usage::

    from src.analyzer.title_generator import generate_post_title

    title = generate_post_title(
        description="...",
        extracted_knowledge="## Topic\\nRutina de glúteos 3 veces por semana\\n...",
        creator_username="@bejaranofit",
    )
    # → "Rutina de glúteos 3 veces por semana"
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_TITLE_CHARS = 120
_MAX_CONTENT_CHARS = 600

_TOPIC_RE = re.compile(
    r"##\s*Topic\s*[:\n\- ]*([^\n#]+)",
    re.IGNORECASE,
)


_PROMPT_TEMPLATE = (
    "Genera un título corto (máximo 8 palabras) que capture la idea principal "
    "de este contenido de @{creator}. "
    "Solo el título, sin comillas, sin explicaciones, sin puntuación al final.\n\n"
    "Contenido:\n{content}"
)


def extract_topic_from_knowledge(extracted_knowledge: str) -> str:
    """Parse the ``## Topic`` line already present in the extraction output.

    Returns an empty string when the section is absent.
    """
    if not extracted_knowledge:
        return ""
    m = _TOPIC_RE.search(extracted_knowledge)
    if not m:
        return ""
    return _clean_title(m.group(1))


def generate_post_title(
    description: str,
    extracted_knowledge: str,
    creator_username: str,
    *,
    llm=None,
) -> str:
    """Return a short descriptive title for a post.

    First tries to parse ``## Topic`` from *extracted_knowledge* (zero extra
    LLM calls — the topic is already there from the main analysis prompt).
    Only falls back to a dedicated LLM call when that section is missing.

    Args:
        description: Raw Instagram caption.
        extracted_knowledge: AI-extracted knowledge text (may contain ``## Topic``).
        creator_username: Creator handle (used in the LLM prompt for context).
        llm: Optional pre-built LLM client.  When *None*, created via
            :class:`~src.llm.factory.LLMClientFactory`.

    Returns:
        A cleaned title string, at most :data:`_MAX_TITLE_CHARS` characters.
    """
    # ── 1. Parse ## Topic from existing extraction output (free) ──────────
    topic = extract_topic_from_knowledge(extracted_knowledge)
    if topic:
        return topic

    # ── 2. Small LLM call (caption-only posts that have no ## Topic) ──────
    raw_content = (extracted_knowledge or description or "").strip()
    if not raw_content:
        return _fallback_title(description)

    content_snippet = raw_content[:_MAX_CONTENT_CHARS]
    creator = (creator_username or "").lstrip("@")
    prompt = _PROMPT_TEMPLATE.format(creator=creator, content=content_snippet)

    if llm is None:
        from src.llm.factory import LLMClientFactory
        llm = LLMClientFactory.get_client(stage="rag")

    try:
        raw_title = llm.generate(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return _clean_title(raw_title) or _fallback_title(description)
    except Exception as exc:
        logger.warning("title_generator: LLM call failed for @%s — %s", creator, exc)
        return _fallback_title(description)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_title(raw: str) -> str:
    """Strip quotes, trailing punctuation, markdown artefacts and whitespace."""
    title = raw.strip().strip('"').strip("'").rstrip(".")
    title = title.lstrip("#* ")
    return title[:_MAX_TITLE_CHARS] if title else ""


_BOILERPLATE_PATTERNS = [
    re.compile(r'^[¡!\s]*comenta\s+(la\s+palabra\s+)?[\w\d_\-]+\s+(y\s+.*?(?:!|\.|\n|$)|si\s+quieres.*?(?:!|\.|\n|$))', re.IGNORECASE),
    re.compile(r'^[¡!\s]*si\s+quieres\s+(que\s+te\s+asesore|mi\s+asesor[ií]a).*?(?:!|\.|\n|$)', re.IGNORECASE),
    re.compile(r'^[¡!\s]*link\s+en\s+mi\s+biograf[ií]a.*?(?:!|\.|\n|$)', re.IGNORECASE),
]


def _fallback_title(description: str) -> str:
    """First clean sentence of the caption, stripping CTA boilerplate and hashtags."""
    lines = [
        l.strip()
        for l in (description or "").splitlines()
        if l.strip() and l.strip() not in ('-', '—', '..', '...', '.')
    ]
    for line in lines:
        cleaned = line
        for pat in _BOILERPLATE_PATTERNS:
            cleaned = pat.sub('', cleaned).strip()
        cleaned = re.sub(r'#\w+', '', cleaned).strip()
        cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', cleaned).strip()
        if len(cleaned) >= 10:
            return _clean_title(cleaned)
    if lines:
        return _clean_title(lines[0])
    return ""

