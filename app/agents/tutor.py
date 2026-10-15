"""Kaigo Sensei (practice tutor) and the Interview Proctor: same grading core, different persona."""
from __future__ import annotations

from ..content import loc

NOTES = {
    "improved": {"en": "You struggled with something similar before, and this time you got it. Real progress!",
                 "ne": "पहिले यस्तै प्रश्नमा गाह्रो भएको थियो, यसपटक सही भयो। राम्रो प्रगति!",
                 "ja": "以前は似た問題で苦戦しましたが、今回はできました。成長しています！"},
    "recurring": {"en": "This is a recurring weak spot for you, so we will come back to it.",
                  "ne": "यो तपाईंको बारम्बार कमजोर हुने क्षेत्र हो, त्यसैले हामी फेरि यसमा फर्कनेछौं।",
                  "ja": "ここは何度かつまずいているところです。また練習しましょう。"},
    "injection": {"en": "Please answer the question itself.",
                  "ne": "कृपया प्रश्नको मात्र उत्तर दिनुहोस्।",
                  "ja": "質問に答えてください。"},
}


class Tutor:
    def __init__(self, deterministic, llm):
        self.deterministic = deterministic   # MockLLM: always available, zero cost
        self.llm = llm                       # configured provider (may also be the mock)

    def grade(self, question: dict, answer: str, lang: str, *, persona: str, use_llm: bool,
              memories: list[dict], knowledge: list[dict], flags: list[str]) -> dict:
        grader = self.llm if (use_llm and getattr(self.llm, "is_llm", False)) else self.deterministic
        context = {"knowledge": [k["text"] for k in knowledge],
                   "memories": [m["text"] for m in memories]}
        result = grader.evaluate(question, answer, lang, persona=persona, context=context)
        result["score"] = max(0.0, min(1.0, float(result["score"])))
        result["grader"] = grader.name + ("+fallback" if result.get("fallback") else "")

        notes = []
        if "prompt_injection" in flags:
            result["score"] = 0.0
            notes.append(NOTES["injection"])
        past_struggle = any(m["kind"] == "struggle" and m.get("question_id") == question["id"] for m in memories) or \
            any(m["kind"] == "struggle" and m["similarity"] > 0.55 for m in memories)
        if past_struggle and result["score"] >= 0.8:
            notes.append(NOTES["improved"])
        elif past_struggle and result["score"] < 0.6:
            notes.append(NOTES["recurring"])
        if notes:
            result["feedback"] = result["feedback"].rstrip() + " " + " ".join(loc(n, lang) for n in notes)
        result["memory_note"] = "improved" if past_struggle and result["score"] >= 0.8 else \
            "recurring" if past_struggle and result["score"] < 0.6 else None
        return result
