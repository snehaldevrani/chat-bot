import json
import time
import threading
from typing import Optional

import numpy as np

_cache_instance: Optional["SemanticCache"] = None
_cache_lock = threading.Lock()


class SemanticCache:
    def __init__(self, similarity_threshold: float = 0.92, ttl: int = 3600):
        self.threshold = similarity_threshold
        self.ttl = ttl
        self._redis = None
        self._memory: list[dict] = []
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()
        self._try_connect_redis()

    def _try_connect_redis(self) -> None:
        try:
            import redis
            from src.config import REDIS_URL
            r = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
            r.ping()
            self._redis = r
        except Exception:
            self._redis = None

    def lookup(self, embedding: list[float]) -> Optional[str]:
        vec = np.array(embedding, dtype=np.float32)
        norm_vec = np.linalg.norm(vec)
        if norm_vec == 0:
            return None

        best_sim, best_response = 0.0, None
        for entry in self._get_all_entries():
            cached_vec = np.array(entry["embedding"], dtype=np.float32)
            sim = float(np.dot(vec, cached_vec) / (norm_vec * np.linalg.norm(cached_vec) + 1e-9))
            if sim > best_sim:
                best_sim, best_response = sim, entry["response"]

        with self._lock:
            if best_sim >= self.threshold and best_response is not None:
                self._hits += 1
                return best_response
            self._misses += 1
        return None

    def store(self, embedding: list[float], response: str, query: str = "") -> None:
        entry = {"embedding": embedding, "response": response, "query": query, "ts": time.time()}
        if self._redis:
            try:
                key = f"rag_cache:{int(time.time() * 1000)}"
                self._redis.setex(key, self.ttl, json.dumps(entry))
                return
            except Exception:
                pass
        with self._lock:
            self._memory.append(entry)
            if len(self._memory) > 500:
                self._memory = self._memory[-500:]

    def _get_all_entries(self) -> list[dict]:
        if self._redis:
            try:
                keys = self._redis.keys("rag_cache:*")
                entries = []
                for k in keys:
                    raw = self._redis.get(k)
                    if raw:
                        entries.append(json.loads(raw))
                return entries
            except Exception:
                pass
        return list(self._memory)

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(self._hits / total * 100, 1) if total > 0 else 0.0,
            "backend": "redis" if self._redis else "memory",
        }


def get_semantic_cache() -> SemanticCache:
    global _cache_instance
    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:
                from src.config import CACHE_SIMILARITY_THRESHOLD, CACHE_TTL
                _cache_instance = SemanticCache(
                    similarity_threshold=CACHE_SIMILARITY_THRESHOLD,
                    ttl=CACHE_TTL,
                )
    return _cache_instance


def reset_semantic_cache() -> None:
    global _cache_instance
    _cache_instance = None
