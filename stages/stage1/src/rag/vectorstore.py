import os
from langchain_chroma import Chroma
from langchain_openai import AzureOpenAIEmbeddings
from src.config import DIAL_API_KEY, DIAL_ENDPOINT, DIAL_API_VERSION, DIAL_EMBEDDING_DEPLOYMENT, CHROMA_PERSIST_DIR
from src.rag.loader import load_and_chunk

_vectorstore: Chroma | None = None


def get_embeddings() -> AzureOpenAIEmbeddings:
    return AzureOpenAIEmbeddings(
        azure_deployment=DIAL_EMBEDDING_DEPLOYMENT,
        azure_endpoint=DIAL_ENDPOINT,
        api_key=DIAL_API_KEY,
        api_version=DIAL_API_VERSION,
    )


def build_vectorstore() -> Chroma:
    chunks = load_and_chunk()
    embeddings = get_embeddings()
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_PERSIST_DIR,
    )
    print(f"ChromaDB built with {len(chunks)} chunks.")
    return vectorstore


def load_vectorstore() -> Chroma:
    embeddings = get_embeddings()
    chroma_dir = CHROMA_PERSIST_DIR
    if os.path.exists(chroma_dir) and os.listdir(chroma_dir):
        return Chroma(
            persist_directory=chroma_dir,
            embedding_function=embeddings,
        )
    return build_vectorstore()


def get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = load_vectorstore()
    return _vectorstore
