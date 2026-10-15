"""Agent graphs on LangGraph, traced to LangSmith and to the app's own database.

    g = AgentGraph("answer")
    g.add_node("guardian.check", "Guardian", guardian_fn)
    g.add_edge(START, "guardian.check")
    g.add_conditional("guardian.check", halted, {"stop": END, "go": "router.grader"})
    state, trace = g.run({...}, metadata={"user_id": 1})

Each node returns (updates, summary, detail). A thin wrapper times the node and records an event; the
events are saved to agent_runs / agent_events (admin "Agent runs" page) and returned to the UI. The same
run appears in LangSmith as a LangGraph trace with every node, OpenAI call, retrieval and Leveler call
nested inside it (when LANGSMITH_TRACING is on).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypedDict

from langgraph.graph import END as LG_END
from langgraph.graph import START as LG_START
from langgraph.graph import StateGraph as LGStateGraph

from ..db import J, Database
from ..errors import BudgetExceeded

START, END = LG_START, LG_END

NodeFn = Callable[[dict], tuple[dict, str, dict]]


class AgentState(TypedDict, total=False):
    """Shared state for every graph (LangGraph needs the keys declared up front)."""
    # who / what
    user: Any; kind: Any; topic_id: Any; session_id: Any; session: Any; turn: Any; question: Any  # noqa: E702
    text: Any; latency_ms: Any; message: Any; history: Any; request: Any  # noqa: E702
    # guardian / router
    budget: Any; flags: Any; use_llm: Any; topic: Any; decision: Any; pool: Any; questions: Any; skill_avg: Any  # noqa: E702
    # memory / retrieval / level
    memories: Any; topic_memories: Any; knowledge: Any; levels: Any; answer_level: Any; query_level: Any; docs: Any  # noqa: E702
    # outputs
    result: Any; tokens: Any; done: Any; eligibility: Any; answer: Any; citations: Any; drafts: Any; report: Any  # noqa: E702
    # control
    halt: Any; error: Any  # noqa: E702


@dataclass
class Event:
    seq: int
    agent: str
    node: str
    status: str
    summary: str
    detail: dict
    duration_ms: int

    def public(self) -> dict:
        return {"seq": self.seq, "agent": self.agent, "node": self.node, "status": self.status,
                "summary": self.summary, "detail": self.detail, "ms": self.duration_ms}


@dataclass
class Trace:
    graph: str
    events: list[Event] = field(default_factory=list)
    status: str = "ok"
    tokens: int = 0
    started: float = field(default_factory=time.perf_counter)

    @property
    def duration_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def public(self, run_id: int | None = None) -> dict:
        return {"run_id": run_id, "graph": self.graph, "status": self.status, "tokens": self.tokens,
                "ms": self.duration_ms, "events": [e.public() for e in self.events], "engine": "langgraph"}


def halted(state: dict) -> str:
    return "stop" if state.get("halt") else "go"


class AgentGraph:
    def __init__(self, name: str):
        self.name = name
        self._nodes: list[tuple[str, str, NodeFn]] = []
        self._edges: list[tuple[str, str]] = []
        self._cond: list[tuple[str, Callable[[dict], str], dict[str, str]]] = []
        self._compiled = None

    def add_node(self, name: str, agent: str, fn: NodeFn) -> "AgentGraph":
        self._nodes.append((name, agent, fn))
        return self

    def add_edge(self, src: str, dst: str) -> "AgentGraph":
        self._edges.append((src, dst))
        return self

    def add_conditional(self, src: str, choose: Callable[[dict], str], mapping: dict[str, str]) -> "AgentGraph":
        self._cond.append((src, choose, mapping))
        return self

    # --------------------------------------------------------------- compile to LangGraph
    @staticmethod
    def _wrap(name: str, agent: str, fn: NodeFn):
        def node(state: AgentState, config) -> dict:
            trace: Trace = config["configurable"]["trace"]
            t0 = time.perf_counter()
            try:
                updates, summary, detail = fn(dict(state))
                status = "ok"
            except BudgetExceeded as e:
                updates, summary, detail, status = {"halt": e}, str(e), {"code": e.code}, "blocked"
            except Exception as e:  # recorded, then re-raised by the caller after the trace is saved
                updates, summary, detail, status = {"error": e}, repr(e)[:300], {}, "error"
            trace.events.append(Event(len(trace.events) + 1, agent, name, status, summary, detail or {},
                                      int((time.perf_counter() - t0) * 1000)))
            if status != "ok":
                trace.status = status
            return updates or {}
        node.__name__ = name.replace(".", "_")
        return node

    def compile(self):
        if self._compiled is not None:
            return self._compiled
        g = LGStateGraph(AgentState)
        for name, agent, fn in self._nodes:
            g.add_node(name, self._wrap(name, agent, fn))
        failed = lambda s: bool(s.get("error"))  # noqa: E731
        for src, dst in self._edges:
            if src == START:
                g.add_edge(START, dst)
            elif dst == END:
                g.add_edge(src, END)
            else:  # stop the run as soon as a node failed
                g.add_conditional_edges(src, (lambda d: (lambda s: END if failed(s) else d))(dst), [dst, END])
        for src, choose, mapping in self._cond:
            targets = sorted(set(mapping.values()) | {END})
            g.add_conditional_edges(src, (lambda c, m: (lambda s: END if failed(s) else m[c(s)]))(choose, mapping), targets)
        self._compiled = g.compile()
        return self._compiled

    def run(self, state: dict, metadata: dict | None = None, tags: list[str] | None = None) -> tuple[dict, Trace]:
        trace = Trace(self.name)
        state.setdefault("tokens", 0)
        out = self.compile().invoke(state, config={
            "configurable": {"trace": trace}, "run_name": f"xplorakodo.{self.name}", "recursion_limit": 60,
            "tags": ["xplorakodo", self.name] + (tags or []), "metadata": metadata or {}})
        trace.tokens = int(out.get("tokens") or 0)
        return out, trace


# Backwards-compatible name used by earlier code.
StateGraph = AgentGraph


def save_trace(db: Database, trace: Trace, user_id: int | None, session_id: int | None) -> int:
    with db.tx() as conn:
        run_id = conn.execute(
            "INSERT INTO agent_runs(graph, user_id, session_id, status, tokens, duration_ms) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (trace.graph, user_id, session_id, trace.status, trace.tokens, trace.duration_ms)).fetchone()["id"]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO agent_events(run_id, seq, agent, node, status, summary, detail, duration_ms) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                [(run_id, e.seq, e.agent, e.node, e.status, e.summary[:500], J(e.detail), e.duration_ms) for e in trace.events])
    return run_id
