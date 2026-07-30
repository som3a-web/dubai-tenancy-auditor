#!/usr/bin/env python3
"""Run a real audit and record it for replay.

    python scripts/record_audit.py samples/sample_1_marina_1br.pdf
    python scripts/record_audit.py --all

Needs a working API key (GEMINI_API_KEY or ANTHROPIC_API_KEY) in the environment
or .streamlit/secrets.toml. Recordings land in samples/recordings/ and are what
the app replays when the live API is unavailable.

A recording is only ever produced from a genuine run. If the run fails, nothing
is written — a partial or fabricated transcript would misrepresent the agent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import agent, replay  # noqa: E402
from src.agent import StepKind  # noqa: E402

SAMPLES_DIR = REPO_ROOT / "samples"


def record_one(pdf_path: Path) -> bool:
    print(f"\n=== {pdf_path.name}")
    steps = []
    provider = model = "unknown"
    failed = None

    for step in agent.run(pdf_path.read_bytes(), filename=pdf_path.name):
        steps.append(step)

        if step.kind is StepKind.PLAN:
            provider = step.payload.get("provider", provider)
            model = step.payload.get("model", model)
            print(f"  provider: {provider}")
        elif step.kind is StepKind.TOOL_CALL:
            print(f"  → {step.tool_name}")
        elif step.kind is StepKind.TOOL_RESULT:
            flag = "ERROR" if step.is_error else "ok"
            first = next(iter(step.display.items()), ("", ""))
            print(f"    {flag}: {first[0]}: {str(first[1])[:80]}")
        elif step.kind is StepKind.DONE:
            model = step.payload.get("model", model)
            print(
                f"  done in {step.payload.get('iterations')} steps, "
                f"{step.payload.get('total_tokens'):,} tokens, "
                f"${step.payload.get('estimated_cost_usd')}"
            )
        elif step.kind in (StepKind.ERROR, StepKind.ABORTED, StepKind.REFUSED):
            failed = f"{step.title}: {step.body}"
            print(f"  FAILED — {failed}")

    if failed:
        print("  not recorded (the run did not succeed)")
        return False

    if not any(s.kind is StepKind.DONE for s in steps):
        print("  not recorded (run produced no completion step)")
        return False

    path = replay.save(steps, pdf_path.name, provider=provider, model=model)
    print(f"  recorded {len(steps)} steps -> {path.relative_to(REPO_ROOT)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="?", type=Path)
    parser.add_argument("--all", action="store_true", help="Record every sample contract.")
    args = parser.parse_args()

    if args.all:
        targets = sorted(SAMPLES_DIR.glob("*.pdf"))
    elif args.pdf:
        targets = [args.pdf]
    else:
        parser.error("give a PDF path or --all")

    if not targets:
        sys.exit("no contracts found")

    results = [record_one(p) for p in targets]
    succeeded = sum(results)
    print(f"\n{succeeded}/{len(results)} recorded.")
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
