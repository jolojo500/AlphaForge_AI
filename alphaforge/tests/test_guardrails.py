"""Mocked unit tests for Amazon Bedrock Guardrails integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from alphaforge.app.bedrock import BedrockConverseClient
from alphaforge.app.guardrails import (
    apply_guardrail,
    guardrail_config,
    load_guardrail_config,
)


@pytest.fixture
def sample_config_dict():
    return {
        "guardrail_id": "test-guardrail-id-123",
        "guardrail_version": "1",
        "guardrail_arn": "arn:aws:bedrock:us-east-1:123456789012:guardrail/test-guardrail-id-123",
        "name": "alphaforge-guardrail",
        "region": "us-east-1",
        "denied_topics": ["personalized-financial-advice", "executing-real-trades", "guaranteed-return-promises"],
        "content_filters": ["SEXUAL", "VIOLENCE", "HATE", "INSULTS", "MISCONDUCT", "PROMPT_ATTACK"],
        "pii_entities": ["EMAIL", "PHONE", "US_BANK_ACCOUNT_NUMBER"],
    }


def test_load_guardrail_config_success(tmp_path: Path, sample_config_dict):
    config_file = tmp_path / "guardrail.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(sample_config_dict, f)

    loaded = load_guardrail_config(config_file)
    assert loaded is not None
    assert loaded["guardrail_id"] == "test-guardrail-id-123"
    assert loaded["guardrail_version"] == "1"
    assert loaded["name"] == "alphaforge-guardrail"
    assert "executing-real-trades" in loaded["denied_topics"]


def test_load_guardrail_config_missing_file(tmp_path: Path):
    missing_file = tmp_path / "does_not_exist.json"
    loaded = load_guardrail_config(missing_file)
    assert loaded is None


def test_load_guardrail_config_invalid_json(tmp_path: Path):
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{not valid json")
    loaded = load_guardrail_config(corrupt_file)
    assert loaded is None


def test_guardrail_config_helper(sample_config_dict):
    # With direct config dict
    cfg = guardrail_config(config=sample_config_dict, trace="enabled")
    assert cfg is not None
    assert cfg["guardrailIdentifier"] == "test-guardrail-id-123"
    assert cfg["guardrailVersion"] == "1"
    assert cfg["trace"] == "enabled"

    # With missing config
    cfg_none = guardrail_config(config=None, config_path=Path("/tmp/non_existent_guardrail_path_123.json"))
    assert cfg_none is None


def test_apply_guardrail_blocked(sample_config_dict):
    mock_client = MagicMock()
    mock_client.apply_guardrail.return_value = {
        "action": "GUARDRAIL_INTERVENED",
        "actionReason": "TOPIC_POLICY",
        "outputs": [
            {
                "text": "AlphaForge est un outil de simulation éducative. Nous n'exécutons aucune transaction réelle."
            }
        ],
        "assessments": [
            {
                "topicPolicy": {
                    "topics": [
                        {
                            "name": "executing-real-trades",
                            "type": "DENY",
                            "action": "BLOCKED",
                            "detected": True,
                        }
                    ]
                }
            }
        ],
    }

    result = apply_guardrail(
        text="Achète 1000 actions TSLA dans mon compte maintenant",
        source="INPUT",
        client=mock_client,
        config_dict=sample_config_dict,
    )

    assert result["blocked"] is True
    assert result["action"] == "GUARDRAIL_INTERVENED"
    assert "AlphaForge est un outil de simulation" in result["message"]
    assert len(result["assessments_summary"]) == 1
    assert result["assessments_summary"][0]["policy"] == "topic"
    assert result["assessments_summary"][0]["name"] == "executing-real-trades"
    assert result["assessments_summary"][0]["action"] == "BLOCKED"

    mock_client.apply_guardrail.assert_called_once_with(
        guardrailIdentifier="test-guardrail-id-123",
        guardrailVersion="1",
        source="INPUT",
        content=[{"text": {"text": "Achète 1000 actions TSLA dans mon compte maintenant"}}],
    )


def test_apply_guardrail_allowed(sample_config_dict):
    mock_client = MagicMock()
    mock_client.apply_guardrail.return_value = {
        "action": "NONE",
        "outputs": [],
        "assessments": [
            {
                "topicPolicy": {
                    "topics": []
                }
            }
        ],
    }

    result = apply_guardrail(
        text="Explique la volatilité de XIU.TO",
        source="INPUT",
        client=mock_client,
        config_dict=sample_config_dict,
    )

    assert result["blocked"] is False
    assert result["action"] == "NONE"
    assert result["message"] == ""
    assert result["assessments_summary"] == []


def test_apply_guardrail_pii_anonymized(sample_config_dict):
    mock_client = MagicMock()
    mock_client.apply_guardrail.return_value = {
        "action": "NONE",
        "outputs": [
            {"text": "Bonjour mon courriel est {EMAIL} et mon tel est {PHONE}"}
        ],
        "assessments": [
            {
                "sensitiveInformationPolicy": {
                    "piiEntities": [
                        {"type": "EMAIL", "action": "ANONYMIZE", "match": "test@example.com"},
                        {"type": "PHONE", "action": "ANONYMIZE", "match": "514-555-1234"},
                    ],
                    "regexes": [],
                }
            }
        ],
    }

    result = apply_guardrail(
        text="Bonjour mon courriel est test@example.com",
        source="INPUT",
        client=mock_client,
        config_dict=sample_config_dict,
    )

    assert result["blocked"] is False
    assert len(result["assessments_summary"]) == 2
    assert result["assessments_summary"][0]["policy"] == "pii"
    assert result["assessments_summary"][0]["type"] == "EMAIL"
    assert result["assessments_summary"][1]["type"] == "PHONE"


def test_apply_guardrail_missing_config_bypass():
    result = apply_guardrail(
        text="Achète 1000 actions TSLA",
        config_dict=None,
        config_path=Path("/tmp/non_existent_guardrail_9876.json"),
    )

    assert result["blocked"] is False
    assert result["action"] == "NONE"
    assert result["reason"] == "guardrail_config_missing"


def test_converse_client_passes_guardrail_config():
    mock_boto_client = MagicMock()
    mock_boto_client.converse.return_value = {
        "output": {"message": {"role": "assistant", "content": [{"text": "Hello"}]}},
        "stopReason": "end_turn",
    }

    client = BedrockConverseClient(client=mock_boto_client)
    g_config = {
        "guardrailIdentifier": "test-id",
        "guardrailVersion": "1",
        "trace": "enabled",
    }

    response = client.converse(
        messages=[{"role": "user", "content": [{"text": "Hello"}]}],
        guardrail_config=g_config,
    )

    assert response is not None
    _, kwargs = mock_boto_client.converse.call_args
    assert "guardrailConfig" in kwargs
    assert kwargs["guardrailConfig"] == g_config
