"""Eval suite: checks the grading pipeline (Guardian scan + Tutor grade) on a golden set.

    python -m evals.run_evals                     # uses LLM_PROVIDER from .env (default: mock)
    LLM_PROVIDER=anthropic python -m evals.run_evals

Questions come from data/*.json, so no database is needed. Exit code is 1 when the pass rate is
below EVAL_THRESHOLD (default 0.9): run it in CI and every time you change a prompt, model or content.
"""
import json
import os
import sys
from pathlib import Path

from app.agents.guardian import Guardian
from app.agents.tutor import Tutor
from app.config import get_settings
from app.llm import MockLLM, make_llm

DATA = Path(__file__).resolve().parent.parent / "data"


def load_questions() -> dict:
    qs = {}
    for name in ("lessons.json", "interview.json"):
        for t in json.loads((DATA / name).read_text(encoding="utf-8"))["topics"]:
            for q in t["questions"]:
                qs[q["id"]] = {**q, "topic_id": t["id"]}
    return qs


def main() -> int:
    llm = make_llm(get_settings())
    tutor = Tutor(MockLLM(), llm)
    questions = load_questions()
    cases = json.loads((Path(__file__).parent / "golden.json").read_text(encoding="utf-8"))
    threshold = float(os.getenv("EVAL_THRESHOLD", "0.9"))
    passed = 0
    print(f"Grader: {llm.name}   cases: {len(cases)}\n")
    for c in cases:
        q = questions[c["question"]]
        persona = "proctor" if q["topic_id"].startswith("interview") else "tutor"
        if not c["answer"].strip():
            score = 0.0
        else:
            res = tutor.grade(q, c["answer"], "en", persona=persona, use_llm=True, memories=[], knowledge=[],
                              flags=Guardian.scan(c["answer"]))
            score = res["score"]
        ok = c["min"] <= score <= c["max"]
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {c['id']:<20} score={score:.2f}  expected {c['min']}-{c['max']}")
    rate = passed / len(cases)
    print(f"\n{passed}/{len(cases)} passed ({rate:.0%}), threshold {threshold:.0%}")
    return 0 if rate >= threshold else 1


if __name__ == "__main__":
    sys.exit(main())
