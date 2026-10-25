from unittest.mock import MagicMock
import pytest
from src.llm.gemini import GeminiLLMClient
from src.rag.query_engine import QueryEngine
from src.indexer.pinecone_indexer import PineconeIndexer


def test_gemini_llm_client_system_instruction_and_generate(monkeypatch):
    client = GeminiLLMClient(api_key="test-key-1,test-key-2")
    assert len(client.clients) == 2
    
    mock_response = MagicMock()
    mock_response.text = "Grounded answer"
    mock_generate = MagicMock(return_value=mock_response)
    
    # Mock models.generate_content
    for c in client.clients:
        monkeypatch.setattr(c.models, "generate_content", mock_generate)
        
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about kettlebell swings."},
    ]
    
    res = client.generate(messages, model="gemini-3.5-flash", temperature=0.3)
    assert res == "Grounded answer"
    
    # Verify generate_content was called on client.models
    call_args = mock_generate.call_args
    assert call_args is not None
    kwargs = call_args.kwargs
    assert kwargs["model"] == "gemini-3.5-flash"
    assert kwargs["contents"] == "Tell me about kettlebell swings."
    assert kwargs["config"].system_instruction == "You are a helpful assistant."
    assert kwargs["config"].temperature == 0.3


def test_gemini_llm_client_rotation_on_429(monkeypatch):
    client = GeminiLLMClient(api_key="test-key-1,test-key-2")
    
    mock_res_success = MagicMock()
    mock_res_success.text = "Success on key 2"
    
    monkeypatch.setattr(
        client.clients[0].models,
        "generate_content",
        MagicMock(side_effect=Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")),
    )
    monkeypatch.setattr(
        client.clients[1].models,
        "generate_content",
        MagicMock(return_value=mock_res_success),
    )
    
    monkeypatch.setattr("time.sleep", lambda s: None)
    
    res = client.generate([{"role": "user", "content": "Hello"}])
    assert res == "Success on key 2"


def test_query_engine_dependency_injection():
    mock_embed = MagicMock()
    mock_embed.get_embedding.return_value = [0.1] * 3072
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "DI response"
    mock_hybrid = MagicMock()
    mock_lexical = MagicMock()
    mock_index = MagicMock()
    
    engine = QueryEngine(
        embed_provider=mock_embed,
        llm=mock_llm,
        hybrid_retriever=mock_hybrid,
        lexical_retriever=mock_lexical,
        pinecone_index=mock_index,
    )
    
    assert engine.embed_provider is mock_embed
    assert engine.llm is mock_llm
    assert engine.hybrid_retriever is mock_hybrid
    assert engine.lexical_retriever is mock_lexical
    assert engine.index is mock_index


def test_pinecone_indexer_update_posts_library(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "test-pc-key")
    
    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index
    mock_pc.list_indexes.return_value = [MagicMock(name="creatorrag")]
    mock_pc.describe_index.return_value = MagicMock(dimension=3072, status=MagicMock(ready=True))
    
    monkeypatch.setattr("src.indexer.pinecone_indexer.Pinecone", lambda **kw: mock_pc)
    monkeypatch.setattr("src.indexer.pinecone_indexer.EmbeddingFactory.get_provider", lambda: MagicMock(dimension=3072))
    
    indexer = PineconeIndexer()
    indexer.index = mock_index
    
    id_creator_map = {"p123": "creator_abc"}
    indexer.update_posts_library(
        post_ids=["p123"],
        library_id="lib_target",
        id_creator_map=id_creator_map,
    )
    
    # Check that update was called with deterministic IDs
    update_calls = mock_index.update.call_args_list
    assert len(update_calls) >= 2
    updated_ids = [call.kwargs.get("id") for call in update_calls]
    assert "p123" in updated_ids
    assert "creator_abc_p123" in updated_ids
    for call in update_calls:
        assert call.kwargs.get("set_metadata") == {"library_id": "lib_target"}

