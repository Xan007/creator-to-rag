from src.rag.evaluation import evaluate_case


def test_retrieval_evaluation_metrics():
    metrics = evaluate_case(["wrong", "right", "other"], ["right"], k=3)
    assert metrics["precision_at_k"] == 1 / 3
    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr"] == 0.5
