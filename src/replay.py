"""Record a real audit and replay it with no API calls.

Why this exists: the demo path depends on an external API, and the free tier is
rate-limited to a handful of requests per minute. A rate limit, a lapsed key or
an outage during a live pitch would otherwise leave nothing to show. A recorded
run replays through the identical UI at zero cost.

Two rules, both load-bearing:

1. **A recording is only ever made from a real run.** There is no synthesiser
   here, and there never should be. Fabricating a transcript and presenting it as
   the agent's reasoning would misrepresent what the system does.
2. **Replays are labelled as replays.** Every recording carries its provenance -
   when it was recorded, against which provider and model - and the UI shows it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.agent import Step, StepKind

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "samples" / "recordings"


def _step_to_dict(step: Step) -> dict:
    data = asdict(step)
    data["kind"] = step.kind.value
    return data


def _step_from_dict(data: dict) -> Step:
    data = dict(data)
    data["kind"] = StepKind(data["kind"])
    return Step(**data)


def save(
    steps: list[Step],
    contract_filename: str,
    provider: str,
    model: str,
    path: Path | None = None,
) -> Path:
    """Write a recorded run to disk. Call only with steps from a real run."""
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    target = path or RECORDINGS_DIR / f"{Path(contract_filename).stem}.json"

    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "contract_filename": contract_filename,
        "provider": provider,
        "model": model,
        "step_count": len(steps),
        "steps": [_step_to_dict(s) for s in steps],
    }
    target.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    return target


def available() -> dict[str, Path]:
    """Recordings on disk, keyed by the contract filename they were made from."""
    if not RECORDINGS_DIR.exists():
        return {}
    found = {}
    for path in sorted(RECORDINGS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            found[data.get("contract_filename", path.stem)] = path
        except (json.JSONDecodeError, OSError):
            continue
    return found


def metadata(path: Path) -> dict:
    data = json.loads(path.read_text())
    return {
        "recorded_at": data.get("recorded_at"),
        "provider": data.get("provider"),
        "model": data.get("model"),
        "contract_filename": data.get("contract_filename"),
        "step_count": data.get("step_count", 0),
    }


def replay(path: Path, pace_seconds: float = 0.45) -> Iterator[Step]:
    """Yield a recorded run's steps, paced so the UI animates as it did live.

    The pacing is cosmetic. It does not pretend the model is running: the caller
    is responsible for labelling the run as a replay.
    """
    import time

    data = json.loads(path.read_text())
    for raw in data.get("steps", []):
        step = _step_from_dict(raw)
        # Tool results carried the real latency; give them a touch longer so the
        # status panels do not all complete at once.
        if pace_seconds:
            time.sleep(pace_seconds * (2 if step.kind is StepKind.TOOL_RESULT else 1))
        yield step
