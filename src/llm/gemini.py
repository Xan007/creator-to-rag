import logging
import os
import time
from typing import Dict, List, Optional
from google import genai
from src.llm.gemini_limits import GEMINI_REQUEST_LIMIT

logger = logging.getLogger(__name__)

FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-flash-lite-latest",
]


class GeminiLLMClient:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")
        self.client = genai.Client(api_key=key)

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"Instructions:\n{content}\n")
            elif role == "user":
                prompt_parts.append(f"User: {content}\n")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}\n")

        full_prompt = "\n".join(prompt_parts).strip()
        models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model] if model else FALLBACK_MODELS

        last_error = None
        for mod in models_to_try:
            if not mod:
                continue
            for attempt in range(4):
                try:
                    with GEMINI_REQUEST_LIMIT:
                        response = self.client.models.generate_content(
                            model=mod,
                            contents=full_prompt,
                        )
                    return response.text.strip()
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    if "404" in err_str or "NOT_FOUND" in err_str:
                        logger.info("Gemini model %s not found (404). Trying next model...", mod)
                        break
                    elif "503" in err_str or "UNAVAILABLE" in err_str:
                        logger.info("Gemini model %s unavailable (503). Trying next model...", mod)
                        break
                    elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        if attempt < 3:
                            wait_seconds = min(30, 5 * (2 ** attempt))
                            logger.info(
                                "Rate limit on %s (429). Retrying in %ss (%d/4)...",
                                mod,
                                wait_seconds,
                                attempt + 1,
                            )
                            time.sleep(wait_seconds)
                        else:
                            logger.info("Rate limit persists on %s (429). Trying next model...", mod)
                            break
                    else:
                        logger.info("Error on model %s: %s. Trying next model...", mod, e)
                        break

        raise RuntimeError(f"All Gemini models failed: {last_error}")

