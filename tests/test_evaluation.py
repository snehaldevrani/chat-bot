import pytest
from src.evaluation.metrics import recall_at_k, precision_at_k, measure_latency, load_test_dataset


# ---------- Recall@K tests ----------

def test_recall_at_k_perfect_retrieval():
    retrieved = ["location_directions.txt", "parking_overview.txt", "faq.txt"]
    relevant = ["location_directions.txt", "parking_overview.txt"]
    assert recall_at_k(retrieved, relevant, k=4) == 1.0


def test_recall_at_k_partial_retrieval():
    retrieved = ["location_directions.txt", "rules_regulations.txt"]
    relevant = ["location_directions.txt", "faq.txt"]
    assert recall_at_k(retrieved, relevant, k=4) == 0.5


def test_recall_at_k_no_relevant_docs():
    assert recall_at_k(["a.txt"], [], k=4) == 0.0


def test_recall_at_k_empty_retrieved():
    assert recall_at_k([], ["faq.txt"], k=4) == 0.0


def test_recall_at_k_respects_k_cutoff():
    retrieved = ["wrong.txt", "wrong2.txt", "faq.txt", "extra.txt"]
    relevant = ["faq.txt"]
    assert recall_at_k(retrieved, relevant, k=2) == 0.0
    assert recall_at_k(retrieved, relevant, k=4) == 1.0


# ---------- Precision@K tests ----------

def test_precision_at_k_perfect():
    retrieved = ["faq.txt", "booking_process.txt"]
    relevant = ["faq.txt", "booking_process.txt", "rules_regulations.txt"]
    assert precision_at_k(retrieved, relevant, k=2) == 1.0


def test_precision_at_k_half():
    retrieved = ["faq.txt", "wrong.txt", "booking_process.txt", "wrong2.txt"]
    relevant = ["faq.txt", "booking_process.txt"]
    assert precision_at_k(retrieved, relevant, k=4) == 0.5


def test_precision_at_k_empty_retrieved():
    assert precision_at_k([], ["faq.txt"], k=4) == 0.0


def test_precision_at_k_no_overlap():
    retrieved = ["wrong1.txt", "wrong2.txt"]
    relevant = ["faq.txt"]
    assert precision_at_k(retrieved, relevant, k=2) == 0.0


# ---------- Latency tests ----------

def test_latency_measurement_returns_correct_result():
    result, latency = measure_latency(lambda x: x * 3, 7)
    assert result == 21
    assert latency >= 0.0


def test_latency_measurement_is_positive():
    _, latency = measure_latency(sum, [1, 2, 3])
    assert latency >= 0.0


def test_latency_measurement_with_kwargs():
    def add(a, b=0):
        return a + b
    result, _ = measure_latency(add, 5, b=10)
    assert result == 15


# ---------- Dataset tests ----------

def test_dataset_loads_successfully():
    dataset = load_test_dataset()
    assert isinstance(dataset, list)
    assert len(dataset) > 0


def test_dataset_has_20_entries():
    dataset = load_test_dataset()
    assert len(dataset) == 20


def test_dataset_entries_have_required_fields():
    dataset = load_test_dataset()
    for item in dataset:
        assert "question" in item
        assert "expected_answer" in item
        assert "relevant_sources" in item


def test_dataset_questions_are_nonempty():
    dataset = load_test_dataset()
    assert all(len(item["question"].strip()) > 0 for item in dataset)


def test_dataset_relevant_sources_are_lists():
    dataset = load_test_dataset()
    assert all(isinstance(item["relevant_sources"], list) for item in dataset)
