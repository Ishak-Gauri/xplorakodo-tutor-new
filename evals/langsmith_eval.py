"""LangSmith evaluations: upload the golden sets as datasets and run experiments.

    export LANGSMITH_API_KEY=...  LANGSMITH_TRACING=true   (and OPENAI_API_KEY + LLM_PROVIDER=openai to test the LLM)
    python -m evals.langsmith_eval            # grader + leveler experiments
    python -m evals.langsmith_eval grader     # just one

Datasets (created once, then reused):
  xplorakodo-grader-golden   39 answers with an expected score range (evals/golden.json)
  xplorakodo-leveler-jlpt    40 Japanese model answers with their JLPT level (data/lessons.json)
Each run shows up under Experiments in LangSmith, so you can compare prompts, models and model versions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from langsmith import Client, evaluate

from app.agents.guardian import Guardian
from app.agents.tutor import Tutor
from app.config import get_settings
from app.llm import MockLLM, make_llm
from app.ml.level_model import LEVELS, LevelEstimator
from evals.run_evals import load_questions

ROOT = Path(__file__).resolve().parent.parent


def ensure_dataset(client: Client, name: str, description: str, rows: list[tuple[dict, dict]]) -> str:
    if client.has_dataset(dataset_name=name):
        return name
    ds = client.create_dataset(dataset_name=name, description=description)
    client.create_examples(inputs=[r[0] for r in rows], outputs=[r[1] for r in rows], dataset_id=ds.id)
    return name


def grader_experiment(client: Client) -> None:
    questions = load_questions()
    golden = json.loads((ROOT / "evals" / "golden.json").read_text(encoding="utf-8"))
    name = ensure_dataset(client, "xplorakodo-grader-golden", "Student answers with the expected score range.",
                          [({"question_id": c["question"], "answer": c["answer"]}, {"min": c["min"], "max": c["max"]}) for c in golden])
    llm = make_llm(get_settings())
    tutor = Tutor(MockLLM(), llm)

    def target(inputs: dict) -> dict:
        q = questions[inputs["question_id"]]
        if not inputs["answer"].strip():
            return {"score": 0.0}
        persona = "proctor" if q["topic_id"].startswith("interview") else "tutor"
        r = tutor.grade(q, inputs["answer"], "en", persona=persona, use_llm=True, memories=[], knowledge=[],
                        flags=Guardian.scan(inputs["answer"]))
        return {"score": r["score"], "grader": r["grader"], "feedback": r["feedback"]}

    def score_in_range(outputs: dict, reference_outputs: dict) -> bool:
        return reference_outputs["min"] <= outputs["score"] <= reference_outputs["max"]

    def absolute_error(outputs: dict, reference_outputs: dict) -> float:
        mid = (reference_outputs["min"] + reference_outputs["max"]) / 2
        return round(abs(outputs["score"] - mid), 3)

    evaluate(target, data=name, evaluators=[score_in_range, absolute_error], experiment_prefix=f"grader-{llm.name}",
             metadata={"grader": llm.name})


def leveler_experiment(client: Client) -> None:
    lessons = json.loads((ROOT / "data" / "lessons.json").read_text(encoding="utf-8"))
    rows = [({"text": q["model_answer"]["ja"]}, {"level": LEVELS[q["difficulty"] - 1]})
            for t in lessons["topics"] if t.get("track") == "jlpt" for q in t["questions"]]
    name = ensure_dataset(client, "xplorakodo-leveler-jlpt", "Japanese sentences with their JLPT level.", rows)
    est = LevelEstimator.load_default()

    def target(inputs: dict) -> dict:
        return est.estimate(inputs["text"])

    def exact_level(outputs: dict, reference_outputs: dict) -> bool:
        return outputs.get("level") == reference_outputs["level"]

    def within_one(outputs: dict, reference_outputs: dict) -> bool:
        return outputs.get("level") is not None and abs(LEVELS.index(outputs["level"]) - LEVELS.index(reference_outputs["level"])) <= 1

    evaluate(target, data=name, evaluators=[exact_level, within_one], experiment_prefix="leveler",
             metadata={"model": est.model.meta.get("trained_at")})


if __name__ == "__main__":
    which = sys.argv[1:] or ["grader", "leveler"]
    c = Client()
    if "grader" in which:
        grader_experiment(c)
    if "leveler" in which:
        leveler_experiment(c)
    print("Done. Open https://smith.langchain.com → Datasets & Experiments.")
