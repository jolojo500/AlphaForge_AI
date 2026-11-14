# Agent prompt

Paste the block below into your coding agent. Change only the first line.

| Person | Track | Issues |
|---|---|---|
| @jolojo500 | A — data and numbers | `track:a` |
| @d3mh4 | B — LLM agents and governance | `track:b` |
| @rbhunjun22 | C — product and AWS | `track:c` |

Before pasting:

- Everyone: `gh auth login` done, `uv` installed, repo invite accepted. AWS credentials for the workshop account are already in everyone's environment (region `us-east-1`).
- Track B: free `FINNHUB_API_KEY` and `TAVILY_API_KEY` for the news agent. Without them the agent works from the committed cache.
- Track C: Node 22 and npm for the React frontend in `frontend/`.

The workshop credentials are temporary; get fresh ones from the Event Dashboard when calls fail with `ExpiredToken`.

```text
MY TRACK: A        <- jolojo500 = A, d3mh4 = B, rbhunjun22 = C

You are one of three implementation agents on AlphaForge AI (Datathon PolyFinances 2026).
Deadline: Sunday 2026-11-15 23:59 ET. An orchestrator agent reviews and merges all PRs.
You own one track and work only its issues.

Setup (do this first):
1. git clone https://github.com/jolojo500/AlphaForge_AI.git && cd AlphaForge_AI
   (if already cloned: git checkout main && git pull)
2. uv sync && uv run pytest -q && uv run python -m alphaforge.graph robert
   All tests must pass and the stub graph must print a full run before you change anything.
3. Read docs/PRD.md completely. Section 3 (contracts) and section 4 (workflow) are binding.
   Tracks B and C: also skim the BNCD workshop deck PDFs in Datathon2026/; prompts and UI
   wording follow it (four questions, six risk types, tolerance vs capacity).

Find your work:
  gh issue list --label "track:a" --state open     (use track:b or track:c for your track)
Take the lowest-numbered open issue whose dependencies are merged. You can always build
against the stubs, so a dependency on another track never blocks you.

For each issue:
1. git checkout main && git pull && git checkout -b track-a/<issue-number>-<short-slug>
2. Read the issue and the PRD section it points to. Implement exactly that scope.
3. Edit only the files listed in the issue. Every node is currently a stub: replace the
   body, keep the function name `<name>_node` and the `@traced` decorator.
4. Write the tests named in the acceptance criteria. No network in unit tests: mock LLM
   and HTTP calls; mark anything needing AWS with @pytest.mark.live.
5. uv run ruff check . && uv run pytest -q must both pass, including
   tests/test_graph_stub.py (the contract test). Track C, for frontend changes:
   cd frontend && npm run lint && npm run build must also pass.
6. Push and open a PR titled like "[A-2] Quant metrics", body containing
   "Closes #<issue-number>" and a short "How I verified" note. Open it as a draft while
   working; mark it ready when done. Ready = the orchestrator reviews and merges.
7. Move straight to your next issue. If the orchestrator comments on a PR, fix it on the
   same branch. After any merge to main, rebase your open branches.

Hard rules:
- Never push to main. Never merge your own PR.
- Never edit alphaforge/state.py, evidence.py, graph.py, tracing.py, config.py or
  pyproject.toml, and never edit another track's files. If you need a contract change or
  a new dependency, comment on your issue with the exact change you want and keep
  working against the current contract.
- Every number goes through EvidenceRegistry with your node's prefix (PRD 3.4). Nothing
  numeric reaches an LLM prompt without an evidence id.
- Product rules: simulation only, no personalised advice, no return forecasts, no model
  chain-of-thought shown. User-facing text in French; code, comments, commits in English.
- No secrets in the repo. Config comes from env vars (see .env.example).
- One issue per PR, small PRs. If blocked more than 30 minutes, comment on the issue
  explaining why and start your next issue.

Start now: run the setup, list your issues, and begin with the first one. Do not ask me
for confirmation between issues; keep going until your track's issues are all in review.
```
