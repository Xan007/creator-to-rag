import logging
import os
from typing import Dict, List, Optional
from src.embeddings.base import BaseEmbeddingProvider
from src.embeddings.gemini import GeminiEmbeddingProvider
from src.embeddings.jina import JinaEmbeddingProvider
from src.embeddings.fastembed_provider import FastEmbedProvider

logger = logging.getLogger(__name__)


class FallbackEmbeddingProvider:
    def __init__(self, primary: Optional[str] = None):
        self.primary_name = primary or os.getenv("EMBED_PROVIDER", "auto").lower()
        self._providers: List[BaseEmbeddingProvider] = []
        self._init_providers()

    def _init_providers(self):
        providers = []

        # Try configuring primary first
        if self.primary_name == "jina" and os.getenv("JINA_API_KEY"):
            providers.append(JinaEmbeddingProvider())
        elif self.primary_name == "gemini" and os.getenv("GEMINI_API_KEY"):
            providers.append(GeminiEmbeddingProvider())
        elif self.primary_name == "fastembed":
            providers.append(FastEmbedProvider())

        # Add remaining available providers to fallback chain
        if os.getenv("JINA_API_KEY") and not any(p.name == "jina" for p in providers):
            providers.append(JinaEmbeddingProvider())

        if os.getenv("GEMINI_API_KEY") and not any(p.name == "gemini" for p in providers):
            providers.append(GeminiEmbeddingProvider())

        if not any(p.name == "fastembed" for p in providers):
            try:
                providers.append(FastEmbedProvider())
            except Exception as e:
                logger.warning("Could not initialize FastEmbed local fallback: %s", e)

        self._providers = providers

    @property
    def name(self) -> str:
        return self._providers[0].name if self._providers else "none"

    @property
    def dimension(self) -> int:
        return self._providers[0].dimension if self._providers else 3072

    def get_embedding(self, text: str, task_type: str = "query") -> List[float]:
        if not self._providers:
            raise RuntimeError("No embedding providers available. Set JINA_API_KEY, GEMINI_API_KEY or install fastembed.")

        errors = []
        for provider in self._providers:
            try:
                return provider.get_embedding(text, task_type=task_type)
            except Exception as e:
                logger.warning("Embedding provider '%s' failed: %s. Trying next provider in fallback chain...", provider.name, e)
                errors.append(f"{provider.name}: {e}")

        raise RuntimeError(f"All embedding providers in fallback chain failed: {'; '.join(errors)}")


class EmbeddingFactory:
    @staticmethod
    def get_provider(provider_type: Optional[str] = None) -> BaseEmbeddingProvider:
        """Return one pinned provider; never switch dimensions mid-index."""
        requested = (provider_type or os.getenv("EMBED_PROVIDER", "auto")).lower()
        if requested == "auto":
            if os.getenv("JINA_API_KEY"):
                requested = "jina"
            elif os.getenv("GEMINI_API_KEY"):
                requested = "gemini"
            else:
                requested = "fastembed"
        if requested == "jina":
            if not os.getenv("JINA_API_KEY"):
                raise RuntimeError("EMBED_PROVIDER=jina requires JINA_API_KEY.")
            return JinaEmbeddingProvider()
        if requested == "gemini":
            if not os.getenv("GEMINI_API_KEY"):
                raise RuntimeError("EMBED_PROVIDER=gemini requires GEMINI_API_KEY.")
            return GeminiEmbeddingProvider()
        if requested == "fastembed":
            return FastEmbedProvider()
        raise ValueError("EMBED_PROVIDER must be auto, jina, gemini, or fastembed.")
