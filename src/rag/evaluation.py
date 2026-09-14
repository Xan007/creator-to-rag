"""Small, dependency-free retrieval evaluation helpers."""

from typing import Iterable, Mapping, Sequence


def precision_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    selected = list(retrieved[:k])
    return sum(item in relevant_set for item in selected) / max(len(selected), 1)


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    return sum(item in relevant_set for item in retrieved[:k]) / len(relevant_set)


def reciprocal_rank(retrieved: Sequence[str], relevant: Iterable[str]) -> float:
    relevant_set = set(relevant)
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def evaluate_case(retrieved: Sequence[str], relevant: Iterable[str], k: int = 5) -> Mapping[str, float]:
    relevant = list(relevant)
    return {
        "precision_at_k": precision_at_k(retrieved, relevant, k),
        "recall_at_k": recall_at_k(retrieved, relevant, k),
        "mrr": reciprocal_rank(retrieved, relevant),
    }
