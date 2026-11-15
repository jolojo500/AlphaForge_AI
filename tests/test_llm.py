import pytest
from pydantic import BaseModel

from alphaforge import config, llm


class Out(BaseModel):
    label: str
    score: float


class FakeMsg:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return FakeMsg(reply)


def test_valid_json_first_try():
    fake = FakeLLM(['{"label": "a", "score": 0.5}'])
    out = llm.call_json("p", Out, llm=fake)
    assert out == Out(label="a", score=0.5)
    assert len(fake.calls) == 1


def test_code_fence_and_prose_are_tolerated():
    fake = FakeLLM(['Voici:\n```json\n{"label": "a", "score": 1}\n```'])
    assert llm.call_json("p", Out, llm=fake).score == 1.0
    fake = FakeLLM(['Sure! {"label": "b", "score": 2} done'])
    assert llm.call_json("p", Out, llm=fake).label == "b"


def test_block_content_lists_are_joined():
    fake = FakeLLM([[{"type": "text", "text": '{"label": "c", '}, {"type": "text", "text": '"score": 3}'}]])
    assert llm.call_json("p", Out, llm=fake).label == "c"


def test_repair_retry_then_success():
    fake = FakeLLM(["not json at all", '{"label": "ok", "score": 1}'])
    out = llm.call_json("p", Out, llm=fake)
    assert out.label == "ok"
    assert len(fake.calls) == 2
    repair = fake.calls[1]
    assert repair[-2] == ("ai", "not json at all")
    assert "not valid" in repair[-1][1]


def test_schema_violation_triggers_repair():
    fake = FakeLLM(['{"label": "x"}', '{"label": "x", "score": 2}'])
    assert llm.call_json("p", Out, llm=fake).score == 2.0


def test_fails_cleanly_after_one_repair():
    fake = FakeLLM(["nope", "still nope"])
    with pytest.raises(llm.LLMError):
        llm.call_json("p", Out, llm=fake)
    assert len(fake.calls) == 2


def test_call_failure_is_wrapped():
    fake = FakeLLM([RuntimeError("ExpiredToken")])
    with pytest.raises(llm.LLMError, match="ExpiredToken"):
        llm.call_json("p", Out, llm=fake)


def test_system_prompt_includes_schema():
    fake = FakeLLM(['{"label": "a", "score": 0}'])
    llm.call_json("p", Out, system="Be brief.", llm=fake)
    role, text = fake.calls[0][0]
    assert role == "system" and text.startswith("Be brief.") and '"score"' in text


def test_model_id_kinds():
    assert llm.model_id("main") and llm.model_id("fast") and llm.model_id("review")
    assert llm.model_id("main") != llm.model_id("fast")
    assert llm.model_id("review") == config.MODEL_REVIEW
    with pytest.raises(ValueError):
        llm.model_id("huge")  # type: ignore[arg-type]


@pytest.mark.live
@pytest.mark.parametrize("kind", ["main", "fast", "review"])
def test_live_bedrock_json(kind):
    out = llm.call_json('Return label "pong" and score 1.', Out, kind=kind)
    assert out.label.lower() == "pong"


# ---- set_llm_override (issue #52)
def test_override_replaces_bedrock_and_can_be_cleared():
    seen = []

    def fn(messages, kind):
        seen.append((kind, messages[-1][0]))
        return '```json\n{"label": "o", "score": 3}\n```'

    llm.set_llm_override(fn)
    try:
        assert llm.call_json("p", Out, kind="fast").label == "o"
    finally:
        llm.set_llm_override(None)
    assert seen == [("fast", "human")]
    assert llm._override is None


def test_override_reply_wrapped_in_prose_and_repair_and_failure():
    replies = iter(["bad", 'Voici: {"label": "r", "score": 1} merci'])
    with llm.llm_override(lambda m, k: next(replies)):
        assert llm.call_json("p", Out).label == "r"
    with llm.llm_override(lambda m, k: "never json"):
        with pytest.raises(llm.LLMError, match="invalid JSON"):
            llm.call_json("p", Out)


def test_override_beats_offline_switch(monkeypatch):
    monkeypatch.setenv("AF_LLM_OFFLINE", "1")
    with pytest.raises(llm.LLMError):
        llm.call_json("p", Out)
    with llm.llm_override(lambda m, k: '{"label": "x", "score": 0}'):
        assert llm.call_json("p", Out).label == "x"


def test_call_is_logged_without_prompt_content(caplog):
    class Msg:
        content = '{"label": "a", "score": 1}'
        usage_metadata = {"input_tokens": 11, "output_tokens": 7}

    class Fake:
        model_id = "test-model"

        def invoke(self, messages):
            return Msg()

    with caplog.at_level("INFO", logger="alphaforge.llm"):
        llm.call_json("SECRET PROMPT TEXT", Out, llm=Fake())
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "test-model" in text and "input_tokens=11" in text and "output_tokens=7" in text
    assert "latency_ms=" in text and "SECRET PROMPT TEXT" not in text
