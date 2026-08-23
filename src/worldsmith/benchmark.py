"""Portable Gate E timing report for a selected target machine."""

from __future__ import annotations

import json
import platform
import sys
import tempfile
import time
from pathlib import Path

from .persistence import load_session, save_session
from .session import WorldSession


def _measure(action) -> float:
    start = time.perf_counter()
    action()
    return round((time.perf_counter() - start) * 1000, 3)


def run_benchmark() -> dict[str, object]:
    """Return stable, human-readable Gate E timing evidence in milliseconds."""
    generation_ms = _measure(lambda: WorldSession.create("Benchmark", 1234))
    session = WorldSession.create("Benchmark", 1234)
    advance_1_ms = _measure(lambda: session.active.advance(1))
    advance_10_ms = _measure(lambda: session.active.advance(10))
    advance_100_ms = _measure(lambda: session.active.advance(100))
    branch_event_id = session.active.events[-1].id
    branch_ms = _measure(lambda: session.branch(branch_event_id, "benchmark-branch"))

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "benchmark.worldsmith.json"
        save_ms = _measure(lambda: save_session(session, path))
        load_ms = _measure(lambda: load_session(path))

    return {
        "machine": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "processor": platform.processor() or "not reported",
        },
        "milliseconds": {
            "world_generation": generation_ms,
            "advance_1_year": advance_1_ms,
            "advance_10_years": advance_10_ms,
            "advance_100_years": advance_100_ms,
            "timeline_branch": branch_ms,
            "save": save_ms,
            "load": load_ms,
        },
        "retained": {
            "timelines": len(session.timelines),
            "events_in_active_timeline": len(session.active.events),
        },
    }


def main() -> None:
    print(json.dumps(run_benchmark(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
