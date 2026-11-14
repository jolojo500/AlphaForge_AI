"""Live integration test against AWS Bedrock Converse API.

Verified under profile 'datathon' in us-east-1.
Single test marked @pytest.mark.bedrock to minimize quota consumption.
"""

import pytest

from alphaforge.app.bedrock import BedrockConverseClient, MODEL_SONNET


@pytest.mark.bedrock
def test_live_bedrock_converse_connection():
    """Verify genuine live Amazon Bedrock Converse API connectivity and model execution."""
    client = BedrockConverseClient(profile_name="datathon", region_name="us-east-1")

    messages = [
        {
            "role": "user",
            "content": [{"text": "Réponds exactement avec les 3 mots: 'AlphaForge Bedrock Connecté'."}],
        }
    ]

    response = client.converse(
        messages=messages,
        model_id=MODEL_SONNET,
        max_tokens=50,
    )

    assert response is not None
    assert response["stopReason"] in ("end_turn", "max_tokens")
    text = BedrockConverseClient.extract_text(response)
    assert len(text) > 0
    assert "AlphaForge" in text or "Bedrock" in text or "Connecté" in text
