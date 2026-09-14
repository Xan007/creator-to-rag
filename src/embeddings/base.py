from typing import List, Protocol, runtime_checkable

@runtime_checkable
class BaseEmbeddingProvider(Protocol):
    def get_embedding(self, text: str, task_type: str = "query") -> List[float]:
        ...

    def get_embeddings(self, texts: List[str], task_type: str = "document") -> List[List[float]]:
        ...

    @property
    def dimension(self) -> int:
        ...

    @property
    def name(self) -> str:
        ...
