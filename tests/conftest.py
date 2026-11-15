import os

import pytest

# Ensure offline deterministic fallback for all test fixtures unless --live is requested
if not any(arg == "--live" for arg in os.sys.argv):
    os.environ.setdefault("AF_LLM_OFFLINE", "1")


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="run tests that need AWS / network")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="live test; pass --live to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _offline_llm(request, monkeypatch):
    """Unit tests never call Bedrock; LLM nodes fall back to their deterministic path."""
    from alphaforge import llm

    if "live" not in request.keywords:
        monkeypatch.setenv("AF_LLM_OFFLINE", "1")
    yield
    llm.set_llm_override(None)
