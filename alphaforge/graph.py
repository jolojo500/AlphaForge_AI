"""Graph wiring (PRD 2). Orchestrator-owned.

    python -m alphaforge.graph robert
    python -m alphaforge.graph amira "J'ai 100 000 $ ..."
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid
from collections.abc import Iterator

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from alphaforge import config
from alphaforge.nodes.events import events_node
from alphaforge.nodes.explain import explain_node
from alphaforge.nodes.macro import macro_node
from alphaforge.nodes.profile import profile_node
from alphaforge.nodes.quant import quant_node
from alphaforge.nodes.red_team import red_team_node
from alphaforge.nodes.scenarios import scenarios_node
from alphaforge.nodes.screening import screening_node
from alphaforge.nodes.verifier import verifier_node
from alphaforge.personas import PERSONAS
from alphaforge.state import GraphState

ANALYSIS = ["quant", "macro", "events"]


def _entry(state: GraphState) -> str:
    # What-if reruns arrive with a profile already set and skip Agent 1.
    return "screening" if state.profile is not None else "profile"


def _after_profile(state: GraphState) -> str:
    # The stub/agent may come back from an interrupt with new text and no profile yet.
    return "screening" if state.profile is not None else "profile"


def _after_red_team(state: GraphState) -> str:
    blocking = any(o.get("severity") == "blocking" for o in state.objections)
    if blocking and state.retries.get("red_team", 0) <= config.MAX_RED_TEAM_LOOPS:
        return "scenarios"
    return "explain"


def _after_verifier(state: GraphState) -> str:
    failed = not (state.verification or {}).get("passed", False)
    if failed and state.retries.get("explain", 0) <= config.MAX_EXPLAIN_RETRIES:
        return "explain"
    return END


def build_graph(checkpointer=None):
    g = StateGraph(GraphState)
    g.add_node("profile", profile_node)
    g.add_node("screening", screening_node)
    g.add_node("quant", quant_node)
    g.add_node("macro", macro_node)
    g.add_node("events", events_node)
    g.add_node("scenarios", scenarios_node)
    g.add_node("red_team", red_team_node)
    g.add_node("explain", explain_node)
    g.add_node("verifier", verifier_node)

    g.add_conditional_edges(START, _entry, ["profile", "screening"])
    g.add_conditional_edges("profile", _after_profile, ["profile", "screening"])
    for n in ANALYSIS:
        g.add_edge("screening", n)
    g.add_edge(ANALYSIS, "scenarios")
    g.add_edge("scenarios", "red_team")
    g.add_conditional_edges("red_team", _after_red_team, ["scenarios", "explain"])
    g.add_edge("explain", "verifier")
    g.add_conditional_edges("verifier", _after_verifier, ["explain", END])
    return g.compile(checkpointer=checkpointer or MemorySaver())


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def initial_state(
    persona: str, request_text: str, as_of_date: dt.date | None = None, profile=None
) -> dict:
    return {
        "persona": persona,
        "request_text": request_text,
        "as_of_date": as_of_date or config.DEFAULT_AS_OF,
        "profile": profile,
    }


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def stream_run(inputs: dict | Command, thread_id: str, graph=None) -> Iterator[dict]:
    """Yield UI events for one run segment.

    {"type": "trace", "entry": {...}}        one per finished node
    {"type": "interrupt", "question": str}   run paused, resume with resume_run()
    {"type": "final", "state": GraphState}   run finished
    """
    graph = graph or get_graph()
    for chunk in graph.stream(inputs, _cfg(thread_id), stream_mode="updates"):
        for node, update in chunk.items():
            if node == "__interrupt__":
                payload = update[0].value
                question = payload.get("question") if isinstance(payload, dict) else str(payload)
                yield {"type": "interrupt", "question": question}
                return
            for entry in (update or {}).get("trace", []):
                yield {"type": "trace", "entry": entry}
    yield {"type": "final", "state": get_state(thread_id, graph)}


def resume_run(answer: str, thread_id: str, graph=None) -> Iterator[dict]:
    """Continue a run paused on a clarifying question."""
    return stream_run(Command(resume=answer), thread_id, graph)


def get_state(thread_id: str, graph=None) -> GraphState:
    graph = graph or get_graph()
    return GraphState.model_validate(graph.get_state(_cfg(thread_id)).values)


def run(
    persona: str,
    request_text: str,
    as_of_date: dt.date | None = None,
    profile=None,
    thread_id: str | None = None,
    graph=None,
) -> GraphState:
    """Blocking helper for tests and scripts. Raises if the run pauses on a question."""
    thread_id = thread_id or uuid.uuid4().hex
    for event in stream_run(initial_state(persona, request_text, as_of_date, profile), thread_id, graph):
        if event["type"] == "interrupt":
            raise RuntimeError(f"run paused on a question: {event['question']}")
        if event["type"] == "final":
            return event["state"]
    raise RuntimeError("run ended without a final state")


if __name__ == "__main__":
    persona = sys.argv[1] if len(sys.argv) > 1 else "robert"
    text = sys.argv[2] if len(sys.argv) > 2 else PERSONAS[persona]["example_request"]
    final = run(persona, text)
    for t in final.trace:
        print(f"[{t['node']:>9}] {t['summary']}")
    print(final.model_dump_json(indent=2, exclude={"trace", "evidence"}))
    print(f"{len(final.evidence)} evidence entries; verification: {final.verification}")
