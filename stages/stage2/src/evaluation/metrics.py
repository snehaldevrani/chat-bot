import json
import time
from pathlib import Path
from typing import List, Dict, Any
from src.config import BASE_DIR


def load_test_dataset() -> List[Dict[str, Any]]:
    path = Path(BASE_DIR) / "src" / "evaluation" / "test_dataset.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def recall_at_k(retrieved_sources: List[str], relevant_sources: List[str], k: int) -> float:
    if not relevant_sources:
        return 0.0
    retrieved_k = set(retrieved_sources[:k])
    relevant = set(relevant_sources)
    return len(retrieved_k & relevant) / len(relevant)


def precision_at_k(retrieved_sources: List[str], relevant_sources: List[str], k: int) -> float:
    retrieved_k = retrieved_sources[:k]
    if not retrieved_k:
        return 0.0
    relevant = set(relevant_sources)
    return sum(1 for r in retrieved_k if r in relevant) / len(retrieved_k)


def measure_latency(func, *args, **kwargs):
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


def run_evaluation(k: int = 4) -> Dict[str, Any]:
    from src.rag.retriever import get_retriever

    dataset = load_test_dataset()
    retriever = get_retriever(k=k)

    recall_scores, precision_scores, latencies = [], [], []

    for item in dataset:
        query = item["question"]
        relevant_sources = item.get("relevant_sources", [])

        docs, latency = measure_latency(retriever.invoke, query)
        latencies.append(latency)

        retrieved_sources = [doc.metadata.get("source", "") for doc in docs]
        recall_scores.append(recall_at_k(retrieved_sources, relevant_sources, k))
        precision_scores.append(precision_at_k(retrieved_sources, relevant_sources, k))

    return {
        "num_queries": len(dataset),
        "k": k,
        "recall_at_k": round(sum(recall_scores) / len(recall_scores), 4) if recall_scores else 0.0,
        "precision_at_k": round(sum(precision_scores) / len(precision_scores), 4) if precision_scores else 0.0,
        "avg_latency_seconds": round(sum(latencies) / len(latencies), 4) if latencies else 0.0,
        "min_latency_seconds": round(min(latencies), 4) if latencies else 0.0,
        "max_latency_seconds": round(max(latencies), 4) if latencies else 0.0,
    }


if __name__ == "__main__":
    print("Running RAG evaluation...")
    results = run_evaluation(k=4)
    print("\nEvaluation Results:")
    print(f"  Queries evaluated : {results['num_queries']}")
    print(f"  k                 : {results['k']}")
    print(f"  Recall@{results['k']}          : {results['recall_at_k']:.4f}")
    print(f"  Precision@{results['k']}       : {results['precision_at_k']:.4f}")
    print(f"  Avg latency       : {results['avg_latency_seconds']:.4f}s")
    print(f"  Min latency       : {results['min_latency_seconds']:.4f}s")
    print(f"  Max latency       : {results['max_latency_seconds']:.4f}s")
