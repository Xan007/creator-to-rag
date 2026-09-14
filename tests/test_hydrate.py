import uuid

from src.pipeline.hydrate import (
    caption_indexed_ids_from_matches,
    overlay_hydrated_knowledge,
    source_ids_from_matches,
)
from storage.db import get_session
from storage.models import Source
import storage.repositories as repo


def _library():
    db = get_session()
    owner = repo.create_user(db, f"hydrate-{uuid.uuid4().hex[:8]}")
    library = repo.create_library(db, owner.id, "Hydrate Lib")
    db.close()
    return library


def test_source_ids_from_matches_includes_top_hit():
    matches = [
        {"score": 0.99, "metadata": {"source_id": "src-top", "url": "https://ig/p/1"}},
        {"score": 0.5, "metadata": {"post_id": "post-2", "url": "https://ig/p/2"}},
    ]
    assert source_ids_from_matches(matches) == ["src-top", "post-2"]


def test_overlay_hydrated_knowledge_replaces_top_hit_caption():
    matches = [
        {
            "score": 0.99,
            "metadata": {
                "source_id": "src-top",
                "extracted_knowledge": "caption only",
                "ingest_status": "caption_indexed",
            },
        }
    ]
    updated = overlay_hydrated_knowledge(matches, {"src-top": "full video knowledge"})
    assert updated[0]["metadata"]["extracted_knowledge"] == "full video knowledge"
    assert updated[0]["metadata"]["ingest_status"] == "full_indexed"


def test_caption_indexed_ids_from_sql_even_when_metadata_missing():
    library = _library()
    db = get_session()
    source = repo.upsert_source(
        db,
        Source(
            id=f"{library.id}:SHORT1",
            library_id=library.id,
            url="https://instagram.com/p/SHORT1",
            platform="instagram",
            author="coach",
            description="Press 4x8",
            extracted_text="Press 4x8",
            status="indexed",
            ingest_status="caption_indexed",
        ),
    )
    full = repo.upsert_source(
        db,
        Source(
            id=f"{library.id}:SHORT2",
            library_id=library.id,
            url="https://instagram.com/p/SHORT2",
            platform="instagram",
            author="coach",
            description="already full",
            extracted_text="video notes",
            status="indexed",
            ingest_status="full_indexed",
        ),
    )
    source_id = source.id
    source_url = source.url
    full_id = full.id
    full_url = full.url
    db.close()

    matches = [
        {"metadata": {"source_id": source_id, "url": source_url}},
        {"metadata": {"source_id": full_id, "url": full_url}},
        {"metadata": {"post_id": "SHORT1", "url": source_url}},
    ]
    needed = caption_indexed_ids_from_matches(matches, library_id=library.id)
    assert source_id in needed
    assert full_id not in needed


def test_list_caption_indexed_post_ids_for_full_reingest():
    library = _library()
    db = get_session()
    repo.upsert_source(
        db,
        Source(
            id=f"{library.id}:ABC123",
            library_id=library.id,
            url="https://instagram.com/p/ABC123",
            platform="instagram",
            author="fitcoach",
            status="indexed",
            ingest_status="caption_indexed",
        ),
    )
    ids = repo.list_caption_indexed_post_ids(db, library.id, "fitcoach")
    db.close()
    assert ids == ["ABC123"]


def test_hydrate_sources_downloads_and_reindexes(monkeypatch):
    from src.pipeline import hydrate as hydrate_mod

    library = _library()
    db = get_session()
    source = repo.upsert_source(
        db,
        Source(
            id="srchydrate01" + uuid.uuid4().hex[:8],
            library_id=library.id,
            url="https://www.tiktok.com/@x/video/1",
            platform="tiktok",
            author="chef",
            title="Pasta",
            description="Pasta 200g",
            extracted_text="Pasta 200g",
            status="indexed",
            ingest_status="caption_indexed",
        ),
    )
    source_id = source.id
    db.close()

    captured = {}

    monkeypatch.setattr(hydrate_mod, "download_with_ytdlp", lambda *a, **k: [{"type": "video", "path": "fake.mp4"}])

    class FakeAnalyzer:
        def __init__(self, *a, **k):
            pass

        def extract_knowledge(self, files, description, **_kwargs):
            captured["files"] = files
            captured["description"] = description
            return "FULL: boil 8 minutes, salt the water"

    class FakeIndexer:
        def __init__(self, *a, **k):
            pass

        def index_source(self, **kwargs):
            captured["index"] = kwargs
            return 2

        def index_post(self, **kwargs):
            captured["post"] = kwargs

    class FakeDownloader:
        def cleanup_items(self, files):
            captured["cleaned"] = files

    monkeypatch.setattr("src.analyzer.gemini_analyzer.GeminiAnalyzer", FakeAnalyzer)
    monkeypatch.setattr("src.indexer.pinecone_indexer.PineconeIndexer", FakeIndexer)
    monkeypatch.setattr("src.downloader.media_downloader.MediaDownloader", FakeDownloader)

    hydrated = hydrate_mod.hydrate_sources([source_id], library_id=library.id)
    assert source_id in hydrated
    assert "FULL: boil 8 minutes" in hydrated[source_id]
    assert captured["files"]
    assert captured["index"]["ingest_status"] == "full_indexed"
    assert captured["index"]["extracted_text"].startswith("FULL:")
