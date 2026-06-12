from unittest.mock import patch, MagicMock
from langchain_core.documents import Document


# ---------- Loader ----------

def test_load_documents_returns_nonempty_list():
    from src.rag.loader import load_documents
    docs = load_documents()
    assert isinstance(docs, list)
    assert len(docs) > 0


def test_documents_have_source_metadata():
    from src.rag.loader import load_documents
    docs = load_documents()
    assert all("source" in doc.metadata for doc in docs)


def test_all_eight_static_files_loaded():
    from src.rag.loader import load_documents
    docs = load_documents()
    assert len(docs) == 8


def test_chunks_have_source_metadata():
    from src.rag.loader import load_and_chunk
    chunks = load_and_chunk()
    assert len(chunks) > 0
    assert all("source" in c.metadata for c in chunks)


# ---------- Vectorstore ----------

@patch("src.rag.vectorstore.AzureOpenAIEmbeddings")
def test_get_embeddings_called_with_correct_deployment(mock_cls):
    mock_cls.return_value = MagicMock()
    from src.rag.vectorstore import get_embeddings
    get_embeddings()
    mock_cls.assert_called_once()
    assert mock_cls.call_args[1].get("azure_deployment") == "text-embedding-3-small-1"


@patch("src.rag.vectorstore.Chroma")
@patch("src.rag.vectorstore.load_and_chunk")
@patch("src.rag.vectorstore.get_embeddings")
def test_build_vectorstore_calls_from_documents(mock_emb, mock_chunk, mock_chroma):
    mock_chunk.return_value = [Document(page_content="test", metadata={"source": "test.txt"})]
    mock_emb.return_value = MagicMock()
    mock_chroma.from_documents.return_value = MagicMock()
    from src.rag.vectorstore import build_vectorstore
    build_vectorstore()
    mock_chroma.from_documents.assert_called_once()


# ---------- Retriever ----------

@patch("src.rag.retriever.load_vectorstore")
def test_get_retriever_returns_object(mock_load):
    from src.rag import retriever as ret_mod
    ret_mod._retriever = None
    mock_vs = MagicMock()
    mock_vs.as_retriever.return_value = MagicMock()
    mock_load.return_value = mock_vs
    from src.rag.retriever import get_retriever
    r = get_retriever()
    assert r is not None


@patch("src.rag.retriever.load_vectorstore")
def test_get_retriever_is_cached(mock_load):
    from src.rag import retriever as ret_mod
    ret_mod._retriever = None
    mock_vs = MagicMock()
    mock_vs.as_retriever.return_value = MagicMock()
    mock_load.return_value = mock_vs
    from src.rag.retriever import get_retriever
    r1 = get_retriever()
    r2 = get_retriever()
    assert r1 is r2
    assert mock_load.call_count == 1


# ---------- Semantic cache ----------

def test_semantic_cache_miss_on_empty():
    from src.rag.semantic_cache import SemanticCache
    cache = SemanticCache(similarity_threshold=0.92)
    result = cache.lookup([1.0, 0.0, 0.0])
    assert result is None


def test_semantic_cache_hit_after_store():
    from src.rag.semantic_cache import SemanticCache
    cache = SemanticCache(similarity_threshold=0.80)
    vec = [1.0, 0.0, 0.0]
    cache.store(vec, "Parking opens at 6am", query="hours?")
    result = cache.lookup(vec)
    assert result == "Parking opens at 6am"


def test_semantic_cache_stats_structure():
    from src.rag.semantic_cache import SemanticCache
    cache = SemanticCache()
    stats = cache.stats()
    assert "hits" in stats
    assert "misses" in stats
    assert "hit_rate_pct" in stats
