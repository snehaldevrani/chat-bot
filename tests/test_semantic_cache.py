import pytest
import numpy as np
from unittest.mock import patch
from src.rag.semantic_cache import SemanticCache, get_semantic_cache, reset_semantic_cache


@pytest.fixture(autouse=True)
def reset_cache():
    reset_semantic_cache()
    yield
    reset_semantic_cache()


def _vec(dim: int = 8, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    v = rng.random(dim).astype(np.float32)
    return (v / np.linalg.norm(v)).tolist()


# ── Basic lookup / store ───────────────────────────────────────────────────────

def test_miss_on_empty_cache():
    cache = SemanticCache(similarity_threshold=0.92)
    assert cache.lookup(_vec(seed=0)) is None


def test_store_and_hit():
    cache = SemanticCache(similarity_threshold=0.92)
    v = _vec(seed=1)
    cache.store(v, "Parking is open 24/7.", "hours question")
    result = cache.lookup(v)
    assert result == "Parking is open 24/7."


def test_near_identical_query_hits():
    cache = SemanticCache(similarity_threshold=0.92)
    v = _vec(seed=2)
    # Slightly perturbed vector still has cosine similarity ~1.0
    perturbed = np.array(v, dtype=np.float32)
    perturbed[0] += 1e-6
    perturbed = (perturbed / np.linalg.norm(perturbed)).tolist()
    cache.store(v, "Regular price is $3/hr.", "price question")
    assert cache.lookup(perturbed) == "Regular price is $3/hr."


def test_orthogonal_vector_misses():
    cache = SemanticCache(similarity_threshold=0.92)
    v1 = _vec(seed=3)
    v2 = _vec(seed=99)  # unrelated random vector, low similarity
    cache.store(v1, "Some response.")
    # Orthogonal vectors have cosine similarity ~0, well below threshold
    assert cache.lookup(v2) is None


# ── Threshold edge cases ───────────────────────────────────────────────────────

def test_lower_threshold_allows_approximate_match():
    cache = SemanticCache(similarity_threshold=0.0)
    v = _vec(seed=5)
    other = _vec(seed=6)
    cache.store(v, "Cached answer.")
    assert cache.lookup(other) == "Cached answer."


def test_threshold_1_0_only_exact_match():
    cache = SemanticCache(similarity_threshold=1.0)
    v = _vec(seed=7)
    perturbed = np.array(v, dtype=np.float32)
    perturbed[0] += 0.1
    perturbed = (perturbed / np.linalg.norm(perturbed)).tolist()
    cache.store(v, "Exact response.")
    assert cache.lookup(perturbed) is None
    assert cache.lookup(v) == "Exact response."


# ── Hit / miss counters ────────────────────────────────────────────────────────

def test_hit_counter_increments():
    cache = SemanticCache(similarity_threshold=0.92)
    v = _vec(seed=8)
    cache.store(v, "response")
    cache.lookup(v)
    cache.lookup(v)
    assert cache.stats()["hits"] == 2


def test_miss_counter_increments():
    cache = SemanticCache(similarity_threshold=0.92)
    cache.lookup(_vec(seed=9))
    cache.lookup(_vec(seed=10))
    assert cache.stats()["misses"] == 2


def test_hit_rate_calculation():
    cache = SemanticCache(similarity_threshold=0.92)
    v = _vec(seed=11)
    cache.store(v, "resp")
    cache.lookup(v)       # hit
    cache.lookup(_vec(seed=12))  # miss
    assert cache.stats()["hit_rate_pct"] == 50.0


def test_stats_zero_before_any_lookup():
    cache = SemanticCache(similarity_threshold=0.92)
    s = cache.stats()
    assert s["hits"] == 0
    assert s["misses"] == 0
    assert s["hit_rate_pct"] == 0.0


# ── Memory eviction ────────────────────────────────────────────────────────────

def test_memory_cap_at_500_entries():
    cache = SemanticCache(similarity_threshold=0.92)
    for i in range(600):
        cache.store(_vec(seed=i), f"resp {i}")
    assert len(cache._memory) <= 500


# ── Backend reporting ──────────────────────────────────────────────────────────

def test_backend_is_memory_without_redis():
    cache = SemanticCache(similarity_threshold=0.92)
    assert cache.stats()["backend"] == "memory"


# ── Singleton ─────────────────────────────────────────────────────────────────

def test_get_semantic_cache_returns_singleton():
    c1 = get_semantic_cache()
    c2 = get_semantic_cache()
    assert c1 is c2


def test_reset_clears_singleton():
    c1 = get_semantic_cache()
    reset_semantic_cache()
    c2 = get_semantic_cache()
    assert c1 is not c2
