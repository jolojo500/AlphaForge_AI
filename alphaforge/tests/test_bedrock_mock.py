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
