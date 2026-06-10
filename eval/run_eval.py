#!/usr/bin/env python3
"""Automated evaluation script for the Multimodal RAG pipeline.

Runs the six golden evaluation questions against the live API and reports:
  - retrieval_hit@k  : Did the correct source page appear in top-k?
  - source_page_accuracy : Is the top-1 source page correct?
  - keyword_recall   : How many expected keywords appear in the answer?
  - latency_ms       : Round-trip time per query.

Usage:
    python eval/run_eval.py                          # default: localhost:8000
    python eval/run_eval.py --base-url http://host:port
    python eval/run_eval.py --document-id my_doc_id
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

GOLDEN_QUESTIONS_PATH = Path(__file__).parent / "golden_questions.json"

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DOCUMENT_ID = "laporan_keuangan_bank_mandiri_2025"
DEFAULT_TOP_K = 5


def load_golden_questions(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_question(
    client: httpx.Client,
    base_url: str,
    document_id: str,
    question_data: dict,
    top_k: int,
) -> dict:
    """Send a single query and evaluate the response."""
    question = question_data["question"]
    expected_pages = set(question_data.get("expected_pages", []))
    expected_keywords = question_data.get("expected_keywords", [])

    payload = {
        "document_id": document_id,
        "question": question,
        "top_k": top_k,
    }

    start = time.perf_counter()
    response = client.post(f"{base_url}/query", json=payload, timeout=60.0)
    latency_ms = (time.perf_counter() - start) * 1000

    if response.status_code != 200:
        return {
            "id": question_data.get("id", ""),
            "question": question,
            "status": "error",
            "error": f"HTTP {response.status_code}: {response.text[:200]}",
            "latency_ms": round(latency_ms),
        }

    data = response.json()
    answer = data.get("answer", "")
    sources = data.get("sources", [])
    retrieved_pages = [s.get("page", 0) for s in sources]

    # Metrics
    retrieval_hit = bool(expected_pages & set(retrieved_pages))
    top1_page = retrieved_pages[0] if retrieved_pages else None
    source_page_correct = top1_page in expected_pages if expected_pages else None

    answer_lower = answer.lower()
    keyword_hits = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    keyword_recall = len(keyword_hits) / len(expected_keywords) if expected_keywords else 1.0

    return {
        "id": question_data.get("id", ""),
        "question": question,
        "status": "ok",
        "answer_preview": answer[:300] + ("..." if len(answer) > 300 else ""),
        "expected_pages": sorted(expected_pages),
        "retrieved_pages": retrieved_pages,
        "retrieval_hit": retrieval_hit,
        "source_page_correct": source_page_correct,
        "keyword_recall": round(keyword_recall, 3),
        "keywords_found": keyword_hits,
        "keywords_missing": [kw for kw in expected_keywords if kw.lower() not in answer_lower],
        "latency_ms": round(latency_ms),
    }


def run_evaluation(
    base_url: str = DEFAULT_BASE_URL,
    document_id: str = DEFAULT_DOCUMENT_ID,
    top_k: int = DEFAULT_TOP_K,
    golden_path: Path = GOLDEN_QUESTIONS_PATH,
) -> dict:
    """Run all golden questions and return aggregated results."""
    questions = load_golden_questions(golden_path)
    results = []

    with httpx.Client() as client:
        # Health check
        try:
            health = client.get(f"{base_url}/health", timeout=5.0)
            if health.status_code != 200:
                print(f"⚠ Health check failed: {health.status_code}")
        except httpx.ConnectError:
            print(f"✗ Cannot connect to {base_url}. Is the API running?")
            sys.exit(1)

        print(f"✓ Connected to {base_url}")
        print(f"  Document: {document_id}")
        print(f"  Questions: {len(questions)}")
        print()

        for i, q in enumerate(questions, 1):
            print(f"[{i}/{len(questions)}] {q['question'][:80]}...")
            result = evaluate_question(client, base_url, document_id, q, top_k)
            results.append(result)

            status = "✓" if result.get("retrieval_hit") else "✗"
            kw_recall = result.get("keyword_recall", 0)
            latency = result.get("latency_ms", 0)
            print(f"  {status} page_hit={result.get('retrieval_hit')} "
                  f"kw_recall={kw_recall:.0%} latency={latency}ms")

    # Aggregate
    ok_results = [r for r in results if r["status"] == "ok"]
    total = len(ok_results)

    summary = {
        "total_questions": len(questions),
        "successful_queries": total,
        "retrieval_hit_at_k": sum(1 for r in ok_results if r["retrieval_hit"]) / total if total else 0,
        "source_page_accuracy": sum(1 for r in ok_results if r["source_page_correct"]) / total if total else 0,
        "avg_keyword_recall": sum(r["keyword_recall"] for r in ok_results) / total if total else 0,
        "avg_latency_ms": round(sum(r["latency_ms"] for r in ok_results) / total) if total else 0,
        "results": results,
    }

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"  Questions tested       : {summary['total_questions']}")
    print(f"  Successful queries     : {summary['successful_queries']}")
    print(f"  Retrieval Hit@{top_k}      : {summary['retrieval_hit_at_k']:.0%}")
    print(f"  Source Page Accuracy   : {summary['source_page_accuracy']:.0%}")
    print(f"  Avg Keyword Recall     : {summary['avg_keyword_recall']:.0%}")
    print(f"  Avg Latency            : {summary['avg_latency_ms']}ms")
    print("=" * 60)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG pipeline with golden questions.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--document-id", default=DEFAULT_DOCUMENT_ID)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--output", type=Path, default=Path("eval/eval_results.json"))
    args = parser.parse_args()

    summary = run_evaluation(
        base_url=args.base_url,
        document_id=args.document_id,
        top_k=args.top_k,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
