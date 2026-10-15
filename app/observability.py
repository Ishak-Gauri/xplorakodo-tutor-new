"""LangSmith tracing.

Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY (and optionally LANGSMITH_PROJECT, default
"xplorakodo-tutor"). Then every LangGraph run, every OpenAI call (via wrap_openai), every retrieval and
every Leveler prediction shows up as a nested trace in smith.langchain.com. Without a key, everything
still works and nothing is sent.
"""
from __future__ import annotations

import functools
import os

os.environ.setdefault("LANGSMITH_PROJECT", "xplorakodo-tutor")

try:  # langsmith is a dependency, but keep the app importable without it
    from langsmith import traceable as _ls_traceable
    from langsmith import utils as _ls_utils
except Exception:  # pragma: no cover
    _ls_traceable = None
    _ls_utils = None


def enabled() -> bool:
    key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    flag = (os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2") or "").lower() in ("1", "true", "yes")
    return bool(key and flag and _ls_traceable)


def status() -> dict:
    return {"enabled": enabled(), "project": os.getenv("LANGSMITH_PROJECT"),
            "endpoint": os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
            "url": "https://smith.langchain.com"}


def traceable(*dargs, **dkwargs):
    """langsmith.traceable when available (it is a no-op while tracing is off), else a pass-through."""
    if _ls_traceable is not None:
        return _ls_traceable(*dargs, **dkwargs)

    def deco(fn):
        @functools.wraps(fn)
        def inner(*a, **k):
            return fn(*a, **k)
        return inner
    if dargs and callable(dargs[0]) and not dkwargs:
        return deco(dargs[0])
    return deco


def wrap_openai_client(client):
    try:
        from langsmith.wrappers import wrap_openai

        return wrap_openai(client)
    except Exception:  # pragma: no cover
        return client
