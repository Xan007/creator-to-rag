import logging
from typing import List
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

FASTEMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
FASTEMBED_DIM = 384


class FastEmbedProvider:
    _model_instance = None

    def __init__(self, model_name: str = FASTEMBED_MODEL):
        if FastEmbedProvider._model_instance is None:
            logger.info("Initializing FastEmbed local ONNX model (%s)...", model_name)
            FastEmbedProvider._model_instance = TextEmbedding(model_name=model_name)
        self.model = FastEmbedProvider._model_instance

    @property
    def name(self) -> str:
        return "fastembed"

    @property
    def dimension(self) -> int:
        return FASTEMBED_DIM

    def get_embedding(self, text: str, task_type: str = "query") -> List[float]:
        # Prefix query if useful, or embed directly
        return self.get_embeddings([text], task_type=task_type)[0]

    def get_embeddings(self, texts: List[str], task_type: str = "document") -> List[List[float]]:
        return [embedding.tolist() for embedding in self.model.embed(texts)]
