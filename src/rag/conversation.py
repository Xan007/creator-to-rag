"""Multi-turn conversation support for the RAG engine.

Design: the CLIENT owns the conversation history and sends it on every
request; this service stays stateless (survives restarts and scale-to-zero,
nothing personal is ever persisted server-side). The engine consumes that
history in two places:

1. Question condensation: follow-up questions like "y para principiantes?"
   are meaningless on their own; they are rewritten into a self-contained
   search query BEFORE embedding/retrieval.
2. Answer generation: a trimmed transcript keeps the answer coherent with
   what was already said.

All helpers are pure or fall back gracefully; a condensation failure must
never break the query itself.
"""
from typing import Any, Dict, List, Tuple

MAX_HISTORY_MESSAGES = 12
MAX_MESSAGE_CHARS = 2000
PROMPT_MAX_MESSAGES = 8
PROMPT_MAX_CHARS = 1200

VALID_ROLES = ("user", "assistant")

CONDENSE_SYSTEM_INSTRUCTION = (
    "You rewrite follow-up questions into fully self-contained search queries "
    "for a knowledge base of fitness/nutrition Instagram posts. Use the "
    "conversation only to resolve pronouns and ellipsis. Reply with ONLY the "
    "rewritten query, same language as the last user message, no explanations."
)


def normalize_history(raw: Any) -> List[Tuple[str, str]]:
    """Validate and trim a raw history payload into [(role, content)] pairs.

    Raises ValueError when the payload is structurally invalid or abusive
    (too many turns). Individual oversized messages are truncated, not rejected.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("history must be a list of {role, content} objects.")
    if len(raw) > MAX_HISTORY_MESSAGES:
        raise ValueError(f"history supports at most {MAX_HISTORY_MESSAGES} messages.")

    pairs: List[Tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("history entries must be objects with role and content.")
        role = item.get("role")
        content = item.get("content")
        if role not in VALID_ROLES:
            raise ValueError(f"history role must be one of {VALID_ROLES}.")
        if not isinstance(content, str):
            raise ValueError("history content must be a string.")
        pairs.append((role, content.strip()[:MAX_MESSAGE_CHARS]))
    return pairs


def build_history_block(pairs: List[Tuple[str, str]]) -> str:
    """Format the trimmed transcript injected into the generation prompt."""
    if not pairs:
        return ""
    recent = pairs[-PROMPT_MAX_MESSAGES:]
    lines = []
    for role, content in recent:
        speaker = "User" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {content[:PROMPT_MAX_CHARS]}")
    return "\n".join(lines)


def build_condense_prompt(question: str, pairs: List[Tuple[str, str]]) -> str:
    """Prompt asking the model to produce a standalone retrieval query."""
    transcript = "\n".join(
        f"{'User' if role == 'user' else 'Assistant'}: {content[:PROMPT_MAX_CHARS]}"
        for role, content in pairs
    )
    return (
        f"{CONDENSE_SYSTEM_INSTRUCTION}\n\n"
        f"Conversation:\n{transcript}\n\n"
        f"Latest user message: {question}\n\n"
        f"Self-contained search query:"
    )


def condense_question(genai_client: Any, model: str, question: str, pairs: List[Tuple[str, str]]) -> str:
    """Rewrite a follow-up into a standalone query; falls back to the original."""
    if not pairs:
        return question
    try:
        prompt = build_condense_prompt(question, pairs)
        if hasattr(genai_client, "models") and hasattr(genai_client.models, "generate_content"):
            response = genai_client.models.generate_content(model=model, contents=prompt)
        elif hasattr(genai_client, "chats"):
            chat = genai_client.chats.create(model=model)
            response = chat.send_message(prompt)
        else:
            return question
        rewritten = (response.text or "").strip()
        return rewritten or question
    except Exception:
        return question
