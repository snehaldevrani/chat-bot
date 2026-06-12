import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from langchain_core.documents import Document
from unittest.mock import patch, MagicMock


# ---------- Loader tests ----------

def test_load_documents_returns_nonempty_list():
    from src.rag.loader import load_documents
    docs = load_documents()
    assert isinstance(docs, list)
    assert len(docs) > 0


def test_documents_have_page_content():
    from src.rag.loader import load_documents
    docs = load_documents()
    assert all(len(doc.page_content.strip()) > 0 for doc in docs)


def test_documents_have_source_metadata():
    from src.rag.loader import load_documents
    docs = load_documents()
    assert all("source" in doc.metadata for doc in docs)


def test_all_eight_static_files_loaded():
    from src.rag.loader import load_documents
    docs = load_documents()
    assert len(docs) == 8


def test_chunks_respect_size_limit():
    from src.rag.loader import load_and_chunk
    from src.config import CHUNK_SIZE
    chunks = load_and_chunk()
    assert len(chunks) > 0
    oversized = [c for c in chunks if len(c.page_content) > CHUNK_SIZE * 1.25]
    assert len(oversized) == 0, f"{len(oversized)} chunks exceed size limit"


def test_chunks_inherit_source_metadata():
    from src.rag.loader import load_and_chunk
    chunks = load_and_chunk()
    assert all("source" in chunk.metadata for chunk in chunks)


# ---------- Vectorstore tests ----------

@patch("src.rag.vectorstore.AzureOpenAIEmbeddings")
def test_get_embeddings_uses_correct_model(mock_cls):
    mock_cls.return_value = MagicMock()
    from src.rag.vectorstore import get_embeddings
    get_embeddings()
    mock_cls.assert_called_once()
    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs.get("azure_deployment") == "text-embedding-3-small-1"


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


# ---------- Retriever tests ----------

@patch("src.rag.retriever.load_vectorstore")
def test_get_retriever_returns_retriever(mock_load_vs):
    from src.rag import retriever as ret_module
    ret_module._retriever = None

    mock_vs = MagicMock()
    mock_vs.as_retriever.return_value = MagicMock()
    mock_load_vs.return_value = mock_vs

    from src.rag.retriever import get_retriever
    retriever = get_retriever()
    assert retriever is not None
    mock_vs.as_retriever.assert_called_once()


@patch("src.rag.retriever.load_vectorstore")
def test_get_retriever_is_cached(mock_load_vs):
    from src.rag import retriever as ret_module
    ret_module._retriever = None

    mock_vs = MagicMock()
    mock_vs.as_retriever.return_value = MagicMock()
    mock_load_vs.return_value = mock_vs

    from src.rag.retriever import get_retriever
    r1 = get_retriever()
    r2 = get_retriever()
    assert r1 is r2
    assert mock_load_vs.call_count == 1
