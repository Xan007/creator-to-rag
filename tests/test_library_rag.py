from src.rag.chunking import chunk_text
from src.rag.hybrid import HybridRetriever


def test_chunk_text_preserves_long_content():
    text = "Sección uno con movilidad.\n\n" + ("detalle importante " * 140)
    chunks = chunk_text(text, max_chars=300, overlap=40)
    assert len(chunks) > 1
    assert "Sección uno" in chunks[0]
    assert all(len(chunk) <= 300 for chunk in chunks)


def test_hybrid_uses_complete_local_corpus_without_dense_hits():
    local = [
        {
            "id": "source:1:0",
            "metadata": {
                "chunk_id": "1:0",
                "url": "https://example.com/1",
                "author": "coach",
                "extracted_knowledge": "La movilidad de cadera mejora con sentadilla profunda.",
            },
        },
        {
            "id": "source:2:0",
            "metadata": {
                "chunk_id": "2:0",
                "url": "https://example.com/2",
                "author": "chef",
                "extracted_knowledge": "La receta usa tomate y aceite.",
            },
        },
    ]
    results = HybridRetriever().retrieve(
        "movilidad cadera",
        pinecone_matches=[],
        local_documents=local,
        top_k=1,
    )
    assert len(results) == 1
    assert results[0]["metadata"]["author"] == "coach"
    assert results[0]["score"] > 0
