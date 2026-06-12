from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.config import STATIC_DATA_DIR, CHUNK_SIZE, CHUNK_OVERLAP


def load_documents() -> list[Document]:
    docs = []
    static_path = Path(STATIC_DATA_DIR)
    for txt_file in sorted(static_path.glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8")
        docs.append(Document(
            page_content=text,
            metadata={"source": txt_file.name, "category": "static"}
        ))
    return docs


def load_and_chunk() -> list[Document]:
    docs = load_documents()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(docs)
    for chunk in chunks:
        if "source" not in chunk.metadata:
            chunk.metadata["source"] = "unknown"
    return chunks
