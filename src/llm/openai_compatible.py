import os
from typing import Dict, List, Optional
from openai import OpenAI


class OpenAICompatibleLLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "gpt-4o-mini",
    ):
        self.client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY"),
            base_url=base_url,
            timeout=45.0,
            max_retries=1,
        )
        self.default_model = default_model

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        target_model = model or self.default_model
        kwargs = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        if not response.choices or not response.choices[0].message.content:
            raise RuntimeError("The language model returned an empty answer.")
        return response.choices[0].message.content.strip()
