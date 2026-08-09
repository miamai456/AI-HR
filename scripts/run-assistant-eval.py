import argparse
import json
from pathlib import Path

import requests

from aihr.evals.assistant_quality import evaluate_assistant_response


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AIHR assistant quality evaluations")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--cases", default="tests/evals/assistant_cases.json")
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    failures = []
    for case in cases:
        response = requests.post(
            f"{args.api_url.rstrip('/')}/assistant/analyze",
            json={
                "context": case["context"],
                "messages": [{"role": "user", "content": case["question"]}],
                "force_refresh": True,
            },
            timeout=90,
        )
        response.raise_for_status()
        violations = evaluate_assistant_response(case, response.json())
        print(f"{case['id']}: {'PASS' if not violations else ', '.join(violations)}")
        if violations:
            failures.append(case["id"])

    print(f"evaluated={len(cases)} failures={len(failures)}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
