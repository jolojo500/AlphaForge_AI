import os

import pytest

# Tests never read the developer's .env (see alphaforge/config.py) and always run with
# authentication off and local backends, whatever the machine has configured.
os.environ["AF_DOTENV"] = "0"
os.environ.setdefault("AF_AUTH", "off")
for _var in ("AF_TRACE_BACKEND", "AF_USERS_BACKEND", "AF_SUITABILITY_BACKEND", "AF_DOSSIER_BACKEND"):
    os.environ.setdefault(_var, "local")
os.environ.setdefault("AF_CHECKPOINTER", "memory")
# The suite never touches the network: no dynamic asset ingestion from Yahoo Finance.
os.environ["AF_DYNAMIC_INGESTION"] = "off"

# Ensure offline deterministic fallback for all test fixtures unless --live is requested
if not any(arg == "--live" for arg in os.sys.argv):
    os.environ.setdefault("AF_LLM_OFFLINE", "1")
    os.environ.setdefault("AF_AUTH", "off")

# The API rate limit and queue are exercised by dedicated tests; keep them out of the way here.
os.environ.setdefault("AF_RATE_LIMIT_RUNS", "100000")
os.environ.setdefault("AF_DAILY_RUN_CAP", "100000")
os.environ.setdefault("AF_MAX_QUEUED_RUNS", "200")
# Background runs from earlier tests must not starve later ones on the shared worker pool.
os.environ.setdefault("AF_MAX_CONCURRENT_RUNS", "16")


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="run tests that need AWS / network")


def pytest_configure(config):
    if not config.getoption("--live"):
        os.environ["AF_LLM_OFFLINE"] = "1"


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
