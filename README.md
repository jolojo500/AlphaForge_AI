# AlphaForge AI

A second-opinion engine for investment decisions. **Simulation only, no personalised advice.**
Datathon PolyFinances 2026 (BNCD + AWS).

- Product, architecture, contracts and who builds what: [docs/PRD.md](docs/PRD.md)
- Work is tracked in the GitHub issues, one track label per agent (`track:a`, `track:b`, `track:c`)
- Prompt to start an agent on a track: [docs/AGENT_PROMPT.md](docs/AGENT_PROMPT.md)

## Quick start

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run python -m alphaforge.graph robert     # runs the whole graph (stub nodes for now)

# frontend (once frontend/ exists)
uv run uvicorn alphaforge.api.server:app --reload
cd frontend && npm install && npm run dev
```

Environment variables are listed in `.env.example`.
