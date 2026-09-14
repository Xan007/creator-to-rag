import logging
import os
from typing import Dict, List, Optional
from config.env import load_runtime_env
from src.llm.base import BaseLLMClient
from src.llm.gemini import GeminiLLMClient
from src.llm.openai_compatible import OpenAICompatibleLLMClient

load_runtime_env()
logger = logging.getLogger(__name__)

# Groq shut down llama-3.3-70b-versatile for free/developer on 2026-08-16.
# Official replacement: https://console.groq.com/docs/deprecations
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"


class FallbackLLMClient:
    def __init__(self, clients: List[BaseLLMClient]):
        self.clients = clients

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        errors = []
        for client in self.clients:
            try:
                return client.generate(messages, model=model, temperature=temperature, json_mode=json_mode)
            except Exception as e:
                logger.warning("LLM client %s failed (%s). Trying next provider...", type(client).__name__, e)
                errors.append(str(e))
        raise RuntimeError(f"All LLM providers failed: {'; '.join(errors)}")


class LLMClientFactory:
    @staticmethod
    def get_client(stage: str = "rag") -> BaseLLMClient:
        load_runtime_env()
        stage_upper = stage.upper()
        provider = os.getenv(f"{stage_upper}_PROVIDER", os.getenv("LLM_PROVIDER", "gemini")).lower()

        if provider == "groq":
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY environment variable is not set.")
            default_model = os.getenv(f"{stage_upper}_MODEL", GROQ_DEFAULT_MODEL)
            return OpenAICompatibleLLMClient(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1",
                default_model=default_model,
            )

        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set.")
            default_model = os.getenv(f"{stage_upper}_MODEL", "gpt-4o-mini")
            return OpenAICompatibleLLMClient(
                api_key=api_key,
                default_model=default_model,
            )

        clients: List[BaseLLMClient] = [GeminiLLMClient()]
        if os.getenv("GROQ_API_KEY"):
            groq_client = OpenAICompatibleLLMClient(
                api_key=os.getenv("GROQ_API_KEY"),
                base_url="https://api.groq.com/openai/v1",
                default_model=GROQ_DEFAULT_MODEL,
            )
            clients.append(groq_client)

        if len(clients) > 1:
            return FallbackLLMClient(clients)
        return clients[0]

