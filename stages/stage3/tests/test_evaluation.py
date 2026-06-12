from src.evaluation.metrics import recall_at_k, precision_at_k, measure_latency, load_test_dataset


# ---------- recall_at_k ----------

def test_recall_perfect():
    assert recall_at_k(["a.txt", "b.txt"], ["a.txt", "b.txt"], k=4) == 1.0


def test_recall_partial():
    assert recall_at_k(["a.txt", "wrong.txt"], ["a.txt", "b.txt"], k=4) == 0.5


def test_recall_empty_relevant():
    assert recall_at_k(["a.txt"], [], k=4) == 0.0


def test_recall_respects_k_cutoff():
    assert recall_at_k(["wrong.txt", "faq.txt"], ["faq.txt"], k=1) == 0.0
    assert recall_at_k(["wrong.txt", "faq.txt"], ["faq.txt"], k=2) == 1.0


# ---------- precision_at_k ----------

def test_precision_perfect():
    assert precision_at_k(["a.txt", "b.txt"], ["a.txt", "b.txt", "c.txt"], k=2) == 1.0


def test_precision_half():
    assert precision_at_k(["a.txt", "wrong.txt"], ["a.txt", "b.txt"], k=2) == 0.5


def test_precision_empty_retrieved():
    assert precision_at_k([], ["a.txt"], k=4) == 0.0


# ---------- measure_latency ----------

def test_latency_returns_correct_result():
    result, elapsed = measure_latency(lambda x: x * 2, 7)
    assert result == 14
    assert elapsed >= 0.0


def test_latency_with_kwargs():
    def add(a, b=0):
        return a + b
    result, _ = measure_latency(add, 5, b=3)
    assert result == 8


# ---------- dataset ----------

def test_dataset_loads():
    data = load_test_dataset()
    assert isinstance(data, list)
    assert len(data) > 0


def test_dataset_has_required_fields():
    for item in load_test_dataset():
        assert "question" in item
        assert "relevant_sources" in item
