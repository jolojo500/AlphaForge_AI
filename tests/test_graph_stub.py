"""Contract tests for the graph. They must stay green as stubs are replaced by real nodes."""

import uuid

import pytest

from alphaforge.evidence import EID_RE, EvidenceRegistry, find_one, numeric
from alphaforge.graph import get_state, initial_state, resume_run, run, stream_run
from alphaforge.personas import PERSONAS
from alphaforge.state import SCENARIO_METRICS, SCENARIO_NAMES

NODES = {"profile", "screening", "quant", "macro", "events", "scenarios", "red_team", "explain", "verifier"}


@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_run_end_to_end(persona):
    s = run(persona, PERSONAS[persona]["example_request"])

    assert s.profile is not None and s.profile.persona == persona
    assert s.eligible_universe
    assert {t["node"] for t in s.trace} == NODES
    assert all(t["summary"] for t in s.trace)

    assert [sc.name for sc in s.scenarios] == list(SCENARIO_NAMES)
    for sc in s.scenarios:
        assert sum(sc.weights.values()) == pytest.approx(1.0)
        assert set(sc.metrics) == set(SCENARIO_METRICS)
        assert all(eid in s.evidence for eid in sc.metrics.values())

    assert all(e["evidence_id"] in s.evidence for e in s.exclusions)
    assert all(EID_RE.fullmatch(k) and v.id == k for k, v in s.evidence.items())
    assert s.explanation["scenario_le_plus_coherent"] in SCENARIO_NAMES
    assert s.verification["passed"] is True


def test_robert_is_judged_and_crypto_excluded():
    s = run("robert", PERSONAS["robert"]["example_request"])
    assert s.profile.request_type == "judge"
    assert s.profile.requested_idea == {"ticker": "TSLA", "weight": 0.25}
    assert s.profile.conflicts
    assert "BTC-USD" not in s.eligible_universe
    assert {e["ticker"] for e in s.exclusions} == {"BTC-USD", "ETH-USD"}


def test_amira_keeps_everything():
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert len(s.eligible_universe) == 31 and not s.exclusions


def test_parallel_branch_merges_all_evidence():
    s = run("mateo", PERSONAS["mateo"]["example_request"])
    assert {k[:2] for k in s.evidence} == {"ES", "EQ", "EM", "EN", "EP"}


def test_interrupt_and_resume():
    tid = uuid.uuid4().hex
    events = list(stream_run(initial_state("amira", ""), tid))
    assert events[-1]["type"] == "interrupt" and events[-1]["question"]

    events = list(resume_run(PERSONAS["amira"]["example_request"], tid))
    assert events[-1]["type"] == "final"
    assert events[-1]["state"].verification["passed"] is True
    assert get_state(tid).request_text == PERSONAS["amira"]["example_request"]


def test_whatif_entry_skips_profile():
    first = run("robert", PERSONAS["robert"]["example_request"])
    changed = first.profile.model_copy(update={"excluded_tickers": ["XIU.TO"]})
    second = run("robert", first.request_text, profile=changed)
    assert "profile" not in {t["node"] for t in second.trace}
    assert "XIU.TO" not in second.eligible_universe


def test_stream_emits_one_trace_event_per_node():
    events = list(stream_run(initial_state("robert", PERSONAS["robert"]["example_request"]), uuid.uuid4().hex))
    assert [e["type"] for e in events].count("final") == 1
    assert {e["entry"]["node"] for e in events if e["type"] == "trace"} == NODES


def test_registry_ids_and_find():
    reg = EvidenceRegistry("EQ")
    import datetime as dt

    a = reg.add({"metric": "volatility_ann", "ticker": "TSLA", "value": 0.58}, "x", dt.date(2026, 1, 1), "m")
    b = reg.add({"metric": "correlation", "tickers": ["SPY", "QQQ"], "value": 0.93}, "x", dt.date(2026, 1, 1), "m")
    assert (a, b) == ("EQ1", "EQ2")
    ev = reg.items()
    assert numeric(find_one(ev, metric="volatility_ann", ticker="TSLA")) == 0.58
    assert find_one(ev, metric="correlation", tickers=["QQQ", "SPY"]).id == "EQ2"
    assert find_one(ev, metric="nope") is None
    with pytest.raises(ValueError):
        EvidenceRegistry("EX")
