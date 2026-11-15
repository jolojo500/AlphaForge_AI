"""Bedrock access for the LLM nodes (PRD 2, Models and AWS). Owned by Track B.

Credentials come from the standard AWS environment (env vars or AWS_PROFILE), never from code.
Model ids and region come from `alphaforge.config`.

Sonnet 5.5 rejects forced `tool_choice`, so structured output is done in the prompt and
validated with Pydantic here, with one repair retry.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from alphaforge import config

ModelKind = Literal["main", "fast"]

MAX_OUTPUT_TOKENS = 4096
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class LLMError(RuntimeError):
    """The model did not return usable JSON after the repair retry, or the call failed."""


def model_id(kind: ModelKind) -> str:
    if kind not in ("main", "fast"):
        raise ValueError(f"unknown model kind {kind!r}; use 'main' or 'fast'")
    return config.MODEL_MAIN if kind == "main" else config.MODEL_FAST


@lru_cache(maxsize=4)
def get_llm(kind: ModelKind = "main"):
    """A cached ChatBedrockConverse for `kind` ('main' = Sonnet, 'fast' = Haiku)."""
    from langchain_aws import ChatBedrockConverse  # lazy: keeps imports cheap in unit tests

    return ChatBedrockConverse(
        model=model_id(kind),
        region_name=config.AWS_REGION,
        max_tokens=MAX_OUTPUT_TOKENS,
    )


def _text_of(message: Any) -> str:
    """Plain text of a LangChain message, whether `content` is a string or a list of blocks."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type", "text") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def extract_json(text: str) -> Any:
    """Parse the first JSON object in `text`, tolerating code fences and surrounding prose."""
    candidates = [text.strip()]
    candidates += [m.strip() for m in _FENCE_RE.findall(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    last_error: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError as exc:
            last_error = exc
    raise ValueError(f"no valid JSON found: {last_error}")


def schema_hint(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), ensure_ascii=False)


def call_json[T: BaseModel](
    prompt: str,
    schema: type[T],
    *,
    kind: ModelKind = "main",
    system: str | None = None,
    llm: Any = None,
) -> T:
    """Ask the model for a JSON object and return it validated against `schema`.

    One repair retry: the model is shown its own reply and the validation error. Raises
    LLMError if the second attempt also fails. `llm` is injectable for tests.
    """
    llm = llm or get_llm(kind)
    instructions = (
        "Reply with a single JSON object that matches this JSON schema. "
        "No prose, no code fences.\n" + schema_hint(schema)
    )
    messages: list[tuple[str, str]] = []
    messages.append(("system", f"{system}\n\n{instructions}" if system else instructions))
    messages.append(("human", prompt))

    last_reply = ""
    error = ""
    for attempt in range(2):
        try:
            last_reply = _text_of(llm.invoke(messages))
        except Exception as exc:  # network, throttling, ExpiredToken, access denied
            raise LLMError(f"model call failed: {type(exc).__name__}: {exc}") from exc
        try:
            return schema.model_validate(extract_json(last_reply))
        except (ValueError, ValidationError) as exc:
            error = str(exc)
            if attempt == 0:
                messages += [
                    ("ai", last_reply),
                    (
                        "human",
                        "Your reply was not valid. Fix it and reply with the corrected JSON "
                        f"object only. Error: {error[:1500]}",
                    ),
                ]
    raise LLMError(f"invalid JSON after one repair attempt: {error[:500]}")
