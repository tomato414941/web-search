import json
import os
import sys

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from web_search.services.search import search_service

EVAL_FILE = "data/evaluation_set.json"


def load_eval_set(path: str) -> list[dict]:
    if not os.path.exists(path):
        print(f"Evaluation file not found at {path}.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_mrr(eval_set: list[dict], k: int = 10) -> float:
    score_sum = 0.0
    for case in eval_set:
        query = case["query"]
        target_url = case["url"]

        # Use SearchService
        res = search_service.search(query, k=k, page=1)

        rank = 0
        for i, hit in enumerate(res["hits"]):
            if hit["url"] == target_url:
                rank = i + 1
                break

        if rank > 0:
            score_sum += 1.0 / rank

    return score_sum / len(eval_set) if eval_set else 0.0


def run_evaluation():
    print("--- Search Relevance Evaluation ---")
    dataset = load_eval_set(EVAL_FILE)
    if not dataset:
        print("No dataset found.")
        return

    mrr = evaluate_mrr(dataset)
    print(f"Queries: {len(dataset)}")
    print(f"MRR (Mean Reciprocal Rank): {mrr:.4f}")


if __name__ == "__main__":
    run_evaluation()
