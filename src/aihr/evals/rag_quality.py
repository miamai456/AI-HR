from __future__ import annotations

import json
from pathlib import Path

from aihr.services.knowledge import DocumentRetriever


def evaluate_rag_cases(retriever: DocumentRetriever, case_path: Path, top_k: int = 3) -> dict:
    cases = json.loads(case_path.read_text(encoding="utf-8"))
    answerable = [case for case in cases if case.get("expected_source")]
    no_answer = [case for case in cases if not case.get("expected_source")]
    hits = 0
    citation_hits = 0
    refused = 0
    for case in cases:
        results = retriever.search(case["question"], top_k=top_k)
        expected = case.get("expected_source")
        if expected:
            matched = [item for item in results if expected in item.source_id]
            hits += int(bool(matched))
            citation_hits += int(bool(matched and "#" in matched[0].source_id))
        else:
            refused += int(not results)
    return {
        "case_count": len(cases),
        "recall_at_k": round(hits / max(len(answerable), 1), 4),
        "citation_accuracy": round(citation_hits / max(len(answerable), 1), 4),
        "no_answer_refusal_rate": round(refused / max(len(no_answer), 1), 4),
        "top_k": top_k,
    }
