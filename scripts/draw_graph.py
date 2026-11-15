"""Draw the LangGraph graph: Mermaid source always, PNG when the mermaid.ink service answers.

    uv run python scripts/draw_graph.py            # writes docs/graph.mmd (+ docs/graph.png if online)
    uv run python scripts/draw_graph.py --no-png   # Mermaid only

The Mermaid file renders on GitHub inside a ```mermaid block and in any Mermaid viewer.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("AF_DOTENV", "0")
os.environ.setdefault("AF_LLM_OFFLINE", "1")
os.environ.setdefault("AF_CHECKPOINTER", "memory")

from alphaforge.graph import get_graph  # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "docs"


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    drawable = get_graph().get_graph()

    mmd = DOCS / "graph.mmd"
    mmd.write_text(drawable.draw_mermaid(), encoding="utf-8")
    print(f"wrote {mmd}")

    if "--no-png" in sys.argv:
        return 0
    try:
        png = drawable.draw_mermaid_png()  # rendered by mermaid.ink, needs network
    except Exception as e:  # noqa: BLE001
        print(f"PNG skipped ({type(e).__name__}: {str(e)[:80]}); the .mmd is complete")
        return 0
    out = DOCS / "graph.png"
    out.write_bytes(png)
    print(f"wrote {out} ({len(png) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
