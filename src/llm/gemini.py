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
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
]


class GeminiLLMClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_keys: List[str] = []
        if api_key:
            self.api_keys = [k.strip() for k in api_key.split(",") if k.strip()]
        else:
            keys_str = os.getenv("GEMINI_API_KEYS")
            if keys_str:
                self.api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
            else:
                key = os.getenv("GEMINI_API_KEY")
                if key:
                    self.api_keys = [k.strip() for k in key.split(",") if k.strip()]

        if not self.api_keys:
            raise ValueError("GEMINI_API_KEY or GEMINI_API_KEYS environment variable is not set.")

        self.clients = [genai.Client(api_key=k) for k in self.api_keys]
        self._client_index = 0

    @property
    def client(self) -> genai.Client:
        return self.clients[self._client_index]

    def _rotate_client(self) -> genai.Client:
        self._client_index = (self._client_index + 1) % len(self.clients)
        return self.clients[self._client_index]

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        # Separate system instructions from conversation turns
        system_parts = [
            msg.get("content", "")
            for msg in messages
            if msg.get("role") == "system" and msg.get("content")
        ]
        system_instruction = "\n\n".join(system_parts).strip() if system_parts else None

        non_system = [msg for msg in messages if msg.get("role") != "system"]

        # Build contents according to official google-genai guidelines
        if not non_system:
            contents = ""
        elif len(non_system) == 1 and non_system[0].get("role", "user") == "user":
            contents = non_system[0].get("content", "")
        else:
            contents = []
            for msg in non_system:
                role = "model" if msg.get("role") == "assistant" else "user"
                contents.append(
                    genai.types.Content(
                        role=role,
                        parts=[genai.types.Part.from_text(text=msg.get("content", ""))],
                    )
                )

        models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model] if model else FALLBACK_MODELS

        last_error = None
        for mod in models_to_try:
            if not mod:
                continue
            gen_config = genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                response_mime_type="application/json" if json_mode else None,
            )
            for attempt in range(4):
                try:
                    with GEMINI_REQUEST_LIMIT:
                        response = self.client.models.generate_content(
                            model=mod,
                            contents=contents,
                            config=gen_config,
                        )
                    return (response.text or "").strip()
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
                        if len(self.clients) > 1:
                            self._rotate_client()
                            logger.info("Rotated to next Gemini API key after 429.")
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

