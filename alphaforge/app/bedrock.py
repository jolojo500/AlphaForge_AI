"""Amazon Bedrock Converse API Client for AlphaForge AI.

Complies with institutional requirements:
- Uses boto3 with adaptive retries and read_timeout=120.
- Connects to Bedrock Runtime in us-east-1 under profile 'datathon' (or env AWS_PROFILE).
- Targets verified models:
    - Sonnet 3.5: global.anthropic.claude-sonnet-5-5 (main orchestrator & explainer)
    - Opus 3.5: global.anthropic.claude-opus-5-5 (governance escalation)
    - Haiku 3.5: global.anthropic.claude-haiku-5-5 (bulk & fast operations)
- Executes tool-use loops without forcing tool_choice.
- Automatically registers all tool outputs into EvidenceRegistry and returns evidence_ids.
- Concatenates non-empty text blocks and omits deprecated inferenceConfig fields (no temperature/top_p conflict).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from alphaforge.app.evidence import EvidenceRegistry
from alphaforge.app.trace import ExecutionTrace

logger = logging.getLogger(__name__)

# Verified AWS Bedrock Model IDs (us-east-1)
MODEL_SONNET = "global.anthropic.claude-sonnet-5-5"
MODEL_OPUS = "global.anthropic.claude-opus-5-5"
MODEL_HAIKU = "global.anthropic.claude-haiku-5-5"


class BedrockConverseClient:
    """Client for Bedrock Converse API with tool-use loop and evidence registration."""

    def __init__(
        self,
        profile_name: str | None = None,
        region_name: str = "us-east-1",
        default_model: str = MODEL_SONNET,
        client: Any = None,
    ):
        self.region_name = region_name
        self.default_model = default_model

        if client is not None:
            self.client = client
        else:
            profile = profile_name or os.environ.get("AWS_PROFILE", "datathon")
            config = Config(
                retries={"mode": "adaptive", "max_attempts": 3},
                read_timeout=120,
                connect_timeout=15,
            )
            try:
                session = boto3.Session(profile_name=profile, region_name=region_name)
                self.client = session.client("bedrock-runtime", config=config)
                logger.info(f"Initialized Bedrock client with profile='{profile}', region='{region_name}'")
            except Exception as e:
                logger.warning(f"Failed to initialize profile '{profile}', falling back to default session: {e}")
                session = boto3.Session(region_name=region_name)
                self.client = session.client("bedrock-runtime", config=config)

    def converse(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        model_id: str | None = None,
        tool_config: dict[str, Any] | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Invoke the Bedrock Converse operation.

        Note: Never sets 'tool_choice' and avoids deprecated 'temperature' parameter.
        """
        model = model_id or self.default_model
        params: dict[str, Any] = {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens},
        }

        if system_prompt:
            params["system"] = [{"text": system_prompt}]

        if tool_config:
            params["toolConfig"] = tool_config

        response = self.client.converse(**params)
        return response

    @staticmethod
    def extract_text(response_or_message: dict[str, Any]) -> str:
        """Extract and concatenate non-empty text blocks from Converse response or message dict."""
        message = response_or_message
        if "output" in response_or_message and "message" in response_or_message["output"]:
            message = response_or_message["output"]["message"]

        content = message.get("content", [])
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                t = block["text"]
                if t:
                    text_parts.append(t)
        return "".join(text_parts).strip()

    def run_tool_loop(
        self,
        messages: list[dict[str, Any]],
        tool_specs: list[dict[str, Any]],
        tool_handlers: dict[str, Callable[..., Any]],
        registry: EvidenceRegistry | None = None,
        trace: ExecutionTrace | None = None,
        system_prompt: str | None = None,
        model_id: str | None = None,
        max_iterations: int = 6,
        max_tokens: int = 4096,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Execute Bedrock Converse multi-turn tool-use loop.

        Args:
            messages: List of conversation messages.
            tool_specs: Bedrock tool definitions in 'toolSpec' format.
            tool_handlers: Mapping of tool_name to callable python handler.
            registry: Optional EvidenceRegistry to register tool results.
            trace: Optional ExecutionTrace to emit observable events.
            system_prompt: Optional system prompt instructions.
            model_id: Target Bedrock model ID.
            max_iterations: Safety cap on tool turns.
            max_tokens: Maximum token generation.

        Returns:
            Tuple of (final_text_response, full_conversation_messages).
        """
        tool_config = {"tools": [{"toolSpec": spec} for spec in tool_specs]} if tool_specs else None
        curr_messages = list(messages)

        for iteration in range(max_iterations):
            response = self.converse(
                messages=curr_messages,
                system_prompt=system_prompt,
                model_id=model_id,
                tool_config=tool_config,
                max_tokens=max_tokens,
            )

            msg = response["output"]["message"]
            stop_reason = response.get("stopReason")
            curr_messages.append(msg)

            # Check if model requested any tool calls
            tool_use_blocks = [
                b["toolUse"] for b in msg.get("content", []) if isinstance(b, dict) and "toolUse" in b
            ]

            if stop_reason == "tool_use" or tool_use_blocks:
                tool_results_content: list[dict[str, Any]] = []

                for tu in tool_use_blocks:
                    tool_id = tu["toolUseId"]
                    tool_name = tu["name"]
                    tool_input = tu.get("input", {})

                    if trace is not None:
                        trace.tool_call(tool=tool_name, args=tool_input)

                    if tool_name not in tool_handlers:
                        error_msg = f"Tool '{tool_name}' is not recognized."
                        logger.error(error_msg)
                        tool_results_content.append({
                            "toolResult": {
                                "toolUseId": tool_id,
                                "content": [{"text": error_msg}],
                                "status": "error",
                            }
                        })
                        continue

                    # Execute deterministic tool handler
                    try:
                        res = tool_handlers[tool_name](**tool_input)

                        # Register tool result as institutional evidence
                        eid = "E_UNREGISTERED"
                        if registry is not None:
                            ev = registry.register(
                                tool=tool_name,
                                args=tool_input,
                                result=res,
                                description=f"Execution of tool {tool_name}",
                            )
                            eid = ev.id
                            if trace is not None:
                                trace.evidence_added(
                                    evidence_id=eid,
                                    tool=tool_name,
                                    summary=f"Result of {tool_name}",
                                    date=ev.date,
                                    currency=ev.currency,
                                )

                        payload: dict[str, Any] = {
                            "evidence_id": eid,
                            "result": res,
                        }
                        tool_results_content.append({
                            "toolResult": {
                                "toolUseId": tool_id,
                                "content": [{"json": payload}],
                                "status": "success",
                            }
                        })
                    except Exception as exc:
                        logger.exception(f"Error executing tool {tool_name}: {exc}")
                        tool_results_content.append({
                            "toolResult": {
                                "toolUseId": tool_id,
                                "content": [{"text": f"Error: {str(exc)}"}],
                                "status": "error",
                            }
                        })

                # Feed tool results back to Converse API as user turn
                curr_messages.append({"role": "user", "content": tool_results_content})

            elif stop_reason in ("end_turn", "stop_sequence") or not tool_use_blocks:
                final_text = self.extract_text(msg)
                return final_text, curr_messages

        # Max iterations reached, return whatever text is available
        last_text = self.extract_text(curr_messages[-1]) if curr_messages else ""
        return last_text, curr_messages
