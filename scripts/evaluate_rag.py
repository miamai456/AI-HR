from __future__ import annotations

import json
from pathlib import Path

from aihr.evals.rag_quality import evaluate_rag_cases
from aihr.services.knowledge import DocumentRetriever

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    metrics = evaluate_rag_cases(
        DocumentRetriever(PROJECT_ROOT / "docs"),
        PROJECT_ROOT / "tests" / "evals" / "rag_cases.json",
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
