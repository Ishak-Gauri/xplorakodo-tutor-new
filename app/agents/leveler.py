"""Leveler agent: the trained JLPT level classifier as a tool other agents call."""
from __future__ import annotations

from ..observability import traceable


class Leveler:
    name = "Leveler"

    def __init__(self, estimator):
        self.estimator = estimator

    @traceable(name="jlpt_leveler", run_type="tool")
    def estimate(self, text: str) -> dict:
        return self.estimator.estimate(text)
