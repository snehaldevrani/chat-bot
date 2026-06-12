import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

# EPAM AI Dial / OpenAI-compatible settings.
DIAL_API_KEY = os.getenv("DIAL_API_KEY", "")
DIAL_ENDPOINT = os.getenv("DIAL_ENDPOINT", "https://ai-proxy.lab.epam.com")
DIAL_API_VERSION = os.getenv("DIAL_API_VERSION", "2024-02-01")
DIAL_LLM_DEPLOYMENT = os.getenv("DIAL_LLM_DEPLOYMENT", "gpt-4o")
DIAL_EMBEDDING_DEPLOYMENT = os.getenv("DIAL_EMBEDDING_DEPLOYMENT", "text-embedding-3-small-1")

# Stage 1 RAG and dynamic-data settings.
CHROMA_PERSIST_DIR = str(BASE_DIR / "data" / "chroma_db")
SQLITE_DB_PATH = str(BASE_DIR / "data" / "dynamic" / "parking.db")
STATIC_DATA_DIR = str(BASE_DIR / "data" / "static")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
RETRIEVER_K = 4

# Optional semantic cache.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_SIMILARITY_THRESHOLD = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.92"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))
