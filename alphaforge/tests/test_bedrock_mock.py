"""Unit tests for Bedrock Converse integration and Agent tool-use loops with mocks."""

import json
from unittest.mock import MagicMock, patch

import pytest

from alphaforge.app.bedrock import BedrockConverseClient, MODEL_SONNET, MODEL_OPUS
from alphaforge.app.evidence import EvidenceRegistry
from alphaforge.app.trace import ExecutionTrace
from alphaforge.app.agents.explainer import ExplainerAgent
from alphaforge.app.agents.governance import GovernanceAgent
from alphaforge.app.personas import get_persona
from alphaforge.app.schemas import ExplanationPayload


def test_bedrock_converse_basic():
    """Verify converse method formats messages and extracts parameters correctly."""
    mock_boto = MagicMock()
    mock_boto.converse.return_value = {
        "stopReason": "end_turn",
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "Bonjour, analyse complétée."}],
            }
        },
    }

    client = BedrockConverseClient(client=mock_boto)
    messages = [{"role": "user", "content": [{"text": "Hello"}]}]
    resp = client.converse(messages=messages, system_prompt="System instructions")

    mock_boto.converse.assert_called_once()
    kwargs = mock_boto.converse.call_args[1]
    assert kwargs["modelId"] == MODEL_SONNET
    assert kwargs["messages"] == messages
    assert kwargs["system"] == [{"text": "System instructions"}]
    # Crucial: temperature must NOT be in inferenceConfig for Sonnet 5.5
    assert "temperature" not in kwargs["inferenceConfig"]
    assert kwargs["inferenceConfig"]["maxTokens"] == 4096

    extracted = BedrockConverseClient.extract_text(resp)
    assert extracted == "Bonjour, analyse complétée."


def test_bedrock_tool_use_loop_mock():
    """Verify multi-turn tool calling loop, evidence registration, and toolResult generation."""
    mock_boto = MagicMock()

    # Turn 1: Model requests tool call 'calc_sum'
    # Turn 2: Model finishes with final text
    mock_boto.converse.side_effect = [
        {
            "stopReason": "tool_use",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "call_123",
                                "name": "calc_sum",
                                "input": {"x": 10, "y": 20},
                            }
                        }
                    ],
                }
            },
        },
        {
            "stopReason": "end_turn",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "Le total calculé est 30."}],
                }
            },
        },
    ]

    client = BedrockConverseClient(client=mock_boto)
    registry = EvidenceRegistry()
    trace = ExecutionTrace()

    tool_specs = [
        {
            "name": "calc_sum",
            "description": "Somme de deux nombres",
            "inputSchema": {"json": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}}}},
        }
    ]
    handlers = {"calc_sum": lambda x, y: {"total": x + y}}

    messages = [{"role": "user", "content": [{"text": "Calcule 10 + 20"}]}]
    final_text, history = client.run_tool_loop(
        messages=messages,
        tool_specs=tool_specs,
        tool_handlers=handlers,
        registry=registry,
        trace=trace,
    )

    assert final_text == "Le total calculé est 30."
    assert mock_boto.converse.call_count == 2

    # Verify tool result registered in evidence
    assert len(registry.list_all()) == 1
    ev = registry.get("E1")
    assert ev.tool == "calc_sum"
    assert ev.result == {"total": 30}

    # Verify toolResult message sent back in history
    tool_res_msg = history[2]
    assert tool_res_msg["role"] == "user"
    assert tool_res_msg["content"][0]["toolResult"]["toolUseId"] == "call_123"
    assert tool_res_msg["content"][0]["toolResult"]["content"][0]["json"]["evidence_id"] == "E1"

    # Verify observable trace events emitted (never internal chain-of-thought)
    event_types = [e.event_type for e in trace.events]
    assert "tool_call" in event_types
    assert "evidence_added" in event_types


def test_explainer_verification_and_regeneration_mock():
    """Verify ExplainerAgent triggers 1 regeneration upon verifier errors and verifies numbers."""
    mock_boto = MagicMock()

    # Attempt 1: Returns payload with ungrounded number 99.99% (fails verification)
    attempt_1 = json.dumps({
        "resume": "Portefeuille conservateur.",
        "quelles_donnees": [{"claim": "Rendement de 99.99%", "evidence_ids": ["E1"]}],
        "pourquoi_ce_choix": [{"claim": "Volatilité de 4.00%", "evidence_ids": ["E1"]}],
        "limites": [{"text": "Biais historique", "type": "methode"}],
        "ce_qui_changerait_la_reponse": ["Hausse des taux"],
        "alertes_gouvernance": [],
    })

    # Attempt 2: Returns payload with grounded numbers (passes verification)
    attempt_2 = json.dumps({
        "resume": "Portefeuille conservateur optimisé.",
        "quelles_donnees": [{"claim": "Volatilité mesurée de 4.00%", "evidence_ids": ["E1"]}],
        "pourquoi_ce_choix": [{"claim": "Allocation équilibrée à 4.00% de vol", "evidence_ids": ["E1"]}],
        "limites": [{"text": "Biais historique", "type": "methode"}],
        "ce_qui_changerait_la_reponse": ["Hausse des taux"],
        "alertes_gouvernance": [],
    })

    mock_boto.converse.side_effect = [
        {"output": {"message": {"role": "assistant", "content": [{"text": attempt_1}]}}},
        {"output": {"message": {"role": "assistant", "content": [{"text": attempt_2}]}}},
    ]

    client = BedrockConverseClient(client=mock_boto)
    registry = EvidenceRegistry()
    registry.register(tool="test_tool", args={}, result={"volatility": 0.0400})  # E1 supports 4.00%

    trace = ExecutionTrace()
    explainer = ExplainerAgent(bedrock_client=client)

    persona = get_persona("robert")
    mock_gov_report = MagicMock(alerts=[])

    payload, report = explainer.generate_explanation(
        persona=persona,
        capital=100000.0,
        user_question="Allocation",
        orchestrator_output={"evidence_ids": {"opt": "E1"}},
        governance_report=mock_gov_report,
        registry=registry,
        trace=trace,
    )

    # Explainer called converse twice (regeneration triggered)
    assert mock_boto.converse.call_count == 2
    assert report.is_valid is True
    assert payload["resume"] == "Portefeuille conservateur optimisé."


def test_trace_event_serialization_excludes_cot():
    """Verify trace records observable events and strictly excludes internal chain-of-thought."""
    trace = ExecutionTrace()
    trace.step_start("Step1", "Initial step")
    trace.tool_call("toolA", {"arg1": 42})
    trace.evidence_added("E1", "toolA", "Summary of E1")
    trace.governance_alert("attention", "rule_esg", "Warning message")
    trace.verification_result(True, 3)
    trace.done("Completed")

    raw_json = trace.to_json()
    parsed = json.loads(raw_json)

    assert len(parsed) == 6
    assert parsed[0]["event_type"] == "step_start"
    assert parsed[1]["event_type"] == "tool_call"
    assert parsed[2]["event_type"] == "evidence_added"
    assert parsed[3]["event_type"] == "governance_alert"
    assert parsed[4]["event_type"] == "verification_result"
    assert parsed[5]["event_type"] == "done"

    # Confirm chain-of-thought is nowhere in output
    for evt in parsed:
        assert "thought" not in evt
        assert "chain_of_thought" not in evt
        assert "thinking" not in evt


def test_request_interpreter_parsing_and_fallback():
    """Verify natural language request interpreter correctly extracts tickers, weights, and intent."""
    from alphaforge.app.agents.interpreter import RequestInterpreterAgent

    interpreter = RequestInterpreterAgent()

    # 1. Robert TSLA 20%
    p1 = interpreter._deterministic_fallback_parse("Je veux mettre 20% de mon portefeuille dans Tesla, qu'en penses-tu ?")
    assert p1.intent == "add_position"
    assert len(p1.requested_positions) == 1
    assert p1.requested_positions[0].ticker == "TSLA"
    assert p1.requested_positions[0].weight == 0.20
    assert p1.out_of_scope is False

    # 2. Amira 100% crypto
    p2 = interpreter._deterministic_fallback_parse("Je veux investir 100% de mon capital dans les cryptomonnaies")
    assert any(pos.ticker == "BTC-USD" for pos in p2.requested_positions)
    assert p2.out_of_scope is False

    # 3. Mateo ENB
    p3 = interpreter._deterministic_fallback_parse("Est-ce que je peux ajouter Enbridge pour son dividende ?")
    assert any(pos.ticker == "ENB.TO" for pos in p3.requested_positions)

    # 4. Unknown ticker & out of scope
    p4 = interpreter._deterministic_fallback_parse("Acheter des options d'achat avec effet de levier sur GameStop")
    assert p4.out_of_scope is True


def test_governance_robert_tsla_natural_language_attention_alert():
    """Verify Robert + TSLA natural language query yields ATTENTION alert, TSLA metrics evidence, and capped alternative."""
    from alphaforge.app.agents.governance import GovernanceAgent
    from alphaforge.app.agents.orchestrator import OrchestratorAgent
    from alphaforge.app.schemas import ParsedRequest, RequestedPosition
    from alphaforge.app.personas import get_persona

    persona = get_persona("robert")
    registry = EvidenceRegistry()
    trace = ExecutionTrace()
    orchestrator = OrchestratorAgent()

    parsed_req = ParsedRequest(
        intent="add_position",
        requested_positions=[RequestedPosition(ticker="TSLA", weight=0.20, company_name="Tesla")],
    )

    out = orchestrator.run(
        persona=persona,
        capital=100000.0,
        parsed_request=parsed_req,
        registry=registry,
        trace=trace,
    )

    governance = GovernanceAgent()
    gov_report = governance.evaluate(
        persona=persona,
        proposed_weights=out["weights"],
        universe_df=out["universe_df"],
        risk_summary_df=out["risk_summary_df"],
        user_requests=["Je veux mettre 20% de mon portefeuille dans Tesla, qu'en penses-tu ?"],
        parsed_request=parsed_req,
        orchestrator_output=out,
        registry=registry,
        trace=trace,
    )

    # Must yield ATTENTION alert
    tsla_alerts = [a for a in gov_report.alerts if "tsla" in a.rule_name.lower()]
    assert len(tsla_alerts) >= 1
    tsla_alert = tsla_alerts[0]
    assert tsla_alert.level == "attention"
    assert "Incohérence" in tsla_alert.message
    assert "Tesla" in tsla_alert.message or "TSLA" in tsla_alert.message
    assert "3.0%" in tsla_alert.message or "satellite" in tsla_alert.message.lower()

    # Must cite evidence IDs
    assert len(tsla_alert.evidence_ids) >= 1

    # Must produce capped alternative
    assert gov_report.capped_alternatives.get("TSLA") == 0.03


def test_governance_amira_100pct_crypto_attention_alert():
    """Verify Amira + 100% crypto yields ATTENTION concentration alert."""
    from alphaforge.app.agents.governance import GovernanceAgent
    from alphaforge.app.schemas import ParsedRequest, RequestedPosition
    from alphaforge.app.personas import get_persona
    import pandas as pd

    persona = get_persona("amira")
    gov = GovernanceAgent()
    parsed_req = ParsedRequest(
        intent="add_position",
        requested_positions=[RequestedPosition(ticker="BTC-USD", weight=1.00, company_name="Bitcoin")],
    )

    dummy_universe = pd.DataFrame([{"ticker": "BTC-USD", "asset_class": "crypto", "sector": "Crypto asset"}])
    report = gov.evaluate(
        persona=persona,
        proposed_weights={"BTC-USD": 0.10, "AAPL": 0.30},
        universe_df=dummy_universe,
        parsed_request=parsed_req,
    )

    crypto_alerts = [a for a in report.alerts if "crypto" in a.rule_name.lower()]
    assert len(crypto_alerts) >= 1
    assert any(a.level == "attention" for a in crypto_alerts)


def test_governance_mateo_enb_esg_tension_alert():
    """Verify Mateo + ENB.TO yields ATTENTION ESG tension alert."""
    from alphaforge.app.agents.governance import GovernanceAgent
    from alphaforge.app.schemas import ParsedRequest, RequestedPosition
    from alphaforge.app.personas import get_persona
    import pandas as pd

    persona = get_persona("mateo")
    gov = GovernanceAgent()
    parsed_req = ParsedRequest(
        intent="add_position",
        requested_positions=[RequestedPosition(ticker="ENB.TO", weight=0.10, company_name="Enbridge")],
    )

    dummy_universe = pd.DataFrame([{"ticker": "ENB.TO", "asset_class": "equity", "sector": "Energy"}])
    report = gov.evaluate(
        persona=persona,
        proposed_weights={"ESGV": 0.15, "XBB.TO": 0.35},
        universe_df=dummy_universe,
        parsed_request=parsed_req,
    )

    esg_alerts = [a for a in report.alerts if "esg" in a.rule_name.lower() or "enbridge" in a.rule_name.lower()]
    assert len(esg_alerts) >= 1
    assert any(a.level == "attention" for a in esg_alerts)


def test_tool_call_trace_data_consistency():
    """Verify every tool_call event consistently exposes details.tool and details.args."""
    trace = ExecutionTrace()
    trace.tool_call("evaluate_asset_addition", {"ticker": "TSLA", "requested_weight": 0.20})

    ev = trace.events[0]
    assert ev.details["tool"] == "evaluate_asset_addition"
    assert ev.details["args"]["ticker"] == "TSLA"
    assert ev.details["data"]["tool"] == "evaluate_asset_addition"
    assert ev.details["data"]["args"]["requested_weight"] == 0.20
