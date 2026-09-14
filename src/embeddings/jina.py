import logging
import os
import time
from typing import List, Optional
import requests
from config.env import load_runtime_env

load_runtime_env()
logger = logging.getLogger(__name__)

JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_MODEL = "jina-embeddings-v3"
JINA_DIM = 1024


class JinaEmbeddingProvider:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("JINA_API_KEY")
        if not self.api_key:
            raise ValueError("JINA_API_KEY environment variable is not set.")

    @property
    def name(self) -> str:
        return "jina"

    @property
    def dimension(self) -> int:
        return JINA_DIM

    def get_embedding(self, text: str, task_type: str = "query") -> List[float]:
        return self.get_embeddings([text], task_type=task_type)[0]

    def get_embeddings(self, texts: List[str], task_type: str = "document") -> List[List[float]]:
        task = "retrieval.query" if task_type == "query" else "retrieval.passage"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": JINA_MODEL,
            "task": task,
            "dimensions": JINA_DIM,
            "input": texts,
        }

        for attempt in range(3):
            try:
                response = requests.post(JINA_API_URL, headers=headers, json=payload, timeout=30)
                if response.status_code == 429:
                    time.sleep((attempt + 1) * 2)
                    continue
                response.raise_for_status()
                data = response.json()
                return [
                    item["embedding"]
                    for item in sorted(data["data"], key=lambda item: item.get("index", 0))
                ]
            except Exception as e:
                if attempt == 2:
                    raise e
                time.sleep(1)

        raise RuntimeError("Failed to fetch Jina embeddings after 3 attempts.")
