import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    """Load a required environment variable; raise clearly if missing or still default."""
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set. "
            f"Add it to your .env file. "
            f"Generate a strong value with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return value

# EPAM AI Dial (OpenAI-compatible proxy)
DIAL_API_KEY = os.getenv("DIAL_API_KEY", "")
DIAL_ENDPOINT = os.getenv("DIAL_ENDPOINT", "https://ai-proxy.lab.epam.com")
DIAL_API_VERSION = os.getenv("DIAL_API_VERSION", "2024-02-01")
DIAL_LLM_DEPLOYMENT = os.getenv("DIAL_LLM_DEPLOYMENT", "gpt-4o")
DIAL_EMBEDDING_DEPLOYMENT = os.getenv("DIAL_EMBEDDING_DEPLOYMENT", "text-embedding-3-small-1")

BASE_DIR = Path(__file__).parent.parent
CHROMA_PERSIST_DIR = str(BASE_DIR / "data" / "chroma_db")
SQLITE_DB_PATH = str(BASE_DIR / "data" / "dynamic" / "parking.db")
STATIC_DATA_DIR = str(BASE_DIR / "data" / "static")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
RETRIEVER_K = 4

# Admin / approval config
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
SENDER_APP_PASSWORD = os.getenv("SENDER_APP_PASSWORD", "")
APPROVAL_SERVER_URL = os.getenv("APPROVAL_SERVER_URL", "http://localhost:8000")
APPROVAL_SERVER_PORT = int(os.getenv("APPROVAL_SERVER_PORT", "8000"))
ADMIN_SECRET_TOKEN = _require_env("ADMIN_SECRET_TOKEN")

# Semantic cache config
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_SIMILARITY_THRESHOLD = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.92"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))

# MCP server config
MCP_SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8001"))
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8001")
MCP_SECRET_TOKEN = _require_env("MCP_SECRET_TOKEN")
RESERVATIONS_FILE = str(BASE_DIR / "data" / "reservations.txt")

# User session config (soft — if absent, sessions invalidate on restart)
import secrets as _secrets
SESSION_SECRET = os.getenv("SESSION_SECRET") or _secrets.token_hex(32)
SESSION_COOKIE_NAME = "citypark_session"
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "7"))
