from langchain_core.vectorstores import VectorStoreRetriever
from src.config import RETRIEVER_K
from src.rag.vectorstore import load_vectorstore

_retriever: VectorStoreRetriever | None = None


def get_retriever(k: int = RETRIEVER_K) -> VectorStoreRetriever:
    global _retriever
    if _retriever is None:
        vs = load_vectorstore()
        _retriever = vs.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k},
        )
    return _retriever


def reset_retriever():
    global _retriever
    _retriever = None
