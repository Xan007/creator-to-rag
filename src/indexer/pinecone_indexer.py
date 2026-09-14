import logging
import os
import time
import hashlib
from typing import Any, Dict, List, Optional

from google import genai
from pinecone import Pinecone, ServerlessSpec
from config.env import getenv, load_runtime_env

load_runtime_env()

logger = logging.getLogger(__name__)

INDEX_NAME = getenv("PINECONE_INDEX", "creatorrag")
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 3072
MAX_CAPTION_CHARS = 1000
MAX_KNOWLEDGE_CHARS = 8000
CHUNK_VERSION = "v2"


from src.embeddings.factory import EmbeddingFactory
from src.rag.chunking import chunk_text

class PineconeIndexer:
    def __init__(self, pinecone_api_key: Optional[str] = None):
        p_key = pinecone_api_key or os.getenv("PINECONE_API_KEY")
        if not p_key:
            raise ValueError("PINECONE_API_KEY environment variable is not set.")
        self.pc = Pinecone(api_key=p_key)
        self.embed_provider = EmbeddingFactory.get_provider()

        self._ensure_index_exists()
        self.index = self.pc.Index(INDEX_NAME)
        self._validate_index_dimension()

    def _ensure_index_exists(self) -> None:
        existing = [i.name for i in self.pc.list_indexes()]
        if INDEX_NAME not in existing:
            dim = self.embed_provider.dimension
            logger.info("Creating Pinecone index '%s' (dim=%d)...", INDEX_NAME, dim)
            self.pc.create_index(
                name=INDEX_NAME,
                dimension=dim,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            while not self.pc.describe_index(name=INDEX_NAME).status.ready:
                logger.info("Waiting for index to be ready...")
                time.sleep(2)

    def _validate_index_dimension(self) -> None:
        """Fail loudly instead of silently mixing incompatible embeddings."""
        try:
            description = self.pc.describe_index(name=INDEX_NAME)
            index_dim = getattr(description, "dimension", None)
            if index_dim is None and isinstance(description, dict):
                index_dim = description.get("dimension")
            if index_dim is not None and int(index_dim) != self.embed_provider.dimension:
                raise ValueError(
                    f"Embedding dimension {self.embed_provider.dimension} does not match "
                    f"Pinecone index dimension {index_dim}. Pin EMBED_PROVIDER or migrate the index."
                )
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("Could not validate Pinecone index dimension: %s", exc)

    def _get_embedding(self, text: str, task_type: str = "document") -> List[float]:
        return self.embed_provider.get_embedding(text, task_type=task_type)

    def _get_embeddings(self, texts: List[str], task_type: str = "document") -> List[List[float]]:
        batch_method = getattr(self.embed_provider, "get_embeddings", None)
        if batch_method is not None:
            return batch_method(texts, task_type=task_type)
        return [self._get_embedding(text, task_type=task_type) for text in texts]


    def index_post(
        self,
        post_id: str,
        url: str,
        creator_username: str,
        post_type: str,
        description: str,
        extracted_text: str,
        library_id: Optional[str] = None,
        ingest_status: str = "full_indexed",
    ) -> None:
        from storage.db import get_session
        from storage.models import Chunk, Post, Source
        import storage.repositories as repo

        indexed_at = time.time()

        db = get_session()
        try:
            post = Post(
                id=post_id,
                url=url,
                creator_username=creator_username,
                type=post_type,
                description=description,
                extracted_knowledge=extracted_text,
                indexed_at=indexed_at,
                library_id=library_id,
                source_id=f"{library_id}:{post_id}" if library_id else None,
            )
            repo.upsert_post(db, post)
            if library_id:
                source_id = f"{library_id}:{post_id}"
                repo.upsert_source(
                    db,
                    Source(
                        id=source_id,
                        library_id=library_id,
                        platform="instagram",
                        content_type=post_type.lower(),
                        url=url,
                        author=creator_username,
                        title=description.splitlines()[0][:200] if description else "",
                        description=description,
                        extracted_text=extracted_text,
                        status="indexed",
                        ingest_status=ingest_status,
                        indexed_at=indexed_at,
                    ),
                )
                pieces = chunk_text(extracted_text or description)
                repo.replace_chunks(
                    db,
                    source_id,
                    library_id,
                    [
                        Chunk(
                            id=f"{source_id}:{ordinal}",
                            source_id=source_id,
                            library_id=library_id,
                            ordinal=ordinal,
                            text=piece,
                            token_count=len(piece.split()),
                        )
                        for ordinal, piece in enumerate(pieces)
                    ],
                )
        finally:
            db.close()

        embed_input = (
            f"Creator: @{creator_username}\n"
            f"URL: {url}\n"
            f"Knowledge Summary:\n{extracted_text}"
        )
        vector_values = self._get_embedding(embed_input)

        vector_id = (
            f"{library_id}:{creator_username}_{post_id}"
            if library_id
            else (f"{creator_username}_{post_id}" if creator_username else post_id)
        )
        meta = {
            "post_id": post_id,
            "creator_username": creator_username or "",
            "url": url,
            "type": post_type,
            "original_description": description[:MAX_CAPTION_CHARS],
            "extracted_knowledge": extracted_text[:MAX_KNOWLEDGE_CHARS],
            "ingest_status": ingest_status,
        }
        if library_id:
            meta.update({
                "library_id": library_id,
                "source_id": f"{library_id}:{post_id}",
                "platform": "instagram",
                "author": creator_username,
                "title": description.splitlines()[0][:200] if description else "",
            })
        self.index.upsert(vectors=[{"id": vector_id, "values": vector_values, "metadata": meta}])
        logger.info("Indexed post %s (@%s) -> Pinecone + DB", post_id, creator_username)

    def index_source(
        self,
        source_id: str,
        library_id: str,
        url: str,
        platform: str,
        author: str,
        title: str,
        description: str,
        extracted_text: str,
        ingest_status: str = "full_indexed",
    ) -> int:
        """Persist and index a source as independently retrievable chunks."""
        from storage.db import get_session
        from storage.models import Chunk, Source
        import storage.repositories as repo

        content = "\n\n".join(filter(None, [title, description, extracted_text]))
        pieces = chunk_text(content)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        db = get_session()
        try:
            old_rows = db.query(Chunk).filter(Chunk.source_id == source_id).all()
            source = repo.upsert_source(
                db,
                Source(
                    id=source_id,
                    library_id=library_id,
                    platform=platform,
                    content_type="video",
                    url=url,
                    author=author,
                    title=title,
                    description=description,
                    extracted_text=extracted_text,
                    status="pending",
                    ingest_status=ingest_status,
                    content_hash=content_hash,
                    chunk_version=CHUNK_VERSION,
                    embedding_provider=self.embed_provider.name,
                    embedding_dimension=self.embed_provider.dimension,
                ),
            )
            chunk_rows = [
                Chunk(
                    id=f"{source_id}:{ordinal}",
                    source_id=source.id,
                    library_id=library_id,
                    ordinal=ordinal,
                    text=piece,
                    token_count=len(piece.split()),
                    chunk_version=CHUNK_VERSION,
                )
                for ordinal, piece in enumerate(pieces)
            ]
            repo.replace_chunks(db, source_id, library_id, chunk_rows)
        finally:
            db.close()

        embedding_inputs = [
            f"Author: {author}\nTitle: {title}\nSource URL: {url}\n{piece}"
            for piece in pieces
        ]
        embeddings = self._get_embeddings(embedding_inputs, task_type="document")
        if len(embeddings) != len(pieces):
            raise RuntimeError(
                f"Embedding provider returned {len(embeddings)} vectors for "
                f"{len(pieces)} chunks."
            )
        vectors = []
        for ordinal, (piece, values) in enumerate(zip(pieces, embeddings)):
            vectors.append(
                {
                    "id": f"source:{library_id}:{source_id}:{ordinal}",
                    "values": values,
                    "metadata": {
                        "source_id": source_id,
                        "chunk_id": f"{source_id}:{ordinal}",
                        "library_id": library_id,
                        "platform": platform,
                        "author": author,
                        "title": title,
                        "url": url,
                        "content_hash": content_hash,
                        "chunk_version": CHUNK_VERSION,
                        "embedding_provider": self.embed_provider.name,
                        "embedding_dimension": self.embed_provider.dimension,
                        "extracted_knowledge": piece[:MAX_KNOWLEDGE_CHARS],
                        "original_description": description[:MAX_CAPTION_CHARS],
                        "ingest_status": ingest_status,
                    },
                }
            )
        if vectors:
            self.index.upsert(vectors=vectors)
            current_ids = {vector["id"] for vector in vectors}
            stale_ids = [
                f"source:{library_id}:{source_id}:{row.ordinal}"
                for row in old_rows
                if f"source:{library_id}:{source_id}:{row.ordinal}" not in current_ids
            ]
            if stale_ids:
                self.index.delete(ids=stale_ids)
        db = get_session()
        try:
            indexed_source = repo.get_source(db, source_id)
            if indexed_source:
                indexed_source.status = "indexed"
                indexed_source.indexed_at = time.time()
                db.commit()
        except Exception:
            failed_source = repo.get_source(db, source_id)
            if failed_source:
                failed_source.status = "failed"
                db.commit()
            raise
        finally:
            db.close()
        logger.info("Indexed source %s in %d chunk(s)", source_id, len(vectors))
        return len(vectors)

    def delete_post(self, post_id: str, creator_username: str = "") -> None:
        vector_id = f"{creator_username}_{post_id}" if creator_username else post_id
        self.index.delete(ids=[vector_id])
        logger.info("Deleted vector %s from Pinecone", vector_id)

