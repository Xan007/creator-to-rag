import uuid

from src.rag.lexical import LexicalRetriever
from storage.db import get_session
from storage.models import Chunk, Source
import storage.repositories as repo


def test_sqlite_lexical_retrieval_is_scoped_to_library():
    db = get_session()
    owner = repo.create_user(db, f"lexical-{uuid.uuid4().hex[:8]}")
    first = repo.create_library(db, owner.id, "Fitness")
    second = repo.create_library(db, owner.id, "Cocina")
    source = repo.upsert_source(
        db,
        Source(
            id=f"source-{uuid.uuid4().hex}",
            library_id=first.id,
            url="https://example.com/fitness",
            platform="tiktok",
            author="coach",
            title="Movilidad de cadera",
            description="rutina",
            extracted_text="sentadilla profunda y movilidad",
        ),
    )
    repo.add_source_to_library(db, second.id, source.id)
    repo.replace_chunks(
        db,
        source.id,
        first.id,
        [Chunk(id=f"{source.id}:0", source_id=source.id, library_id=first.id, ordinal=0, text="sentadilla profunda y movilidad")],
    )
    first_id, second_id = first.id, second.id
    db.close()

    assert LexicalRetriever().retrieve("movilidad", first_id)
    assert LexicalRetriever().retrieve("movilidad", second_id)
