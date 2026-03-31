#!/usr/bin/env python3
"""Emit a machine-readable software gate report for CI artifacts."""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path


def _is_nonempty_file(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument(
        "--resilience-metrics",
        required=True,
        help="JSON metrics emitted by tests/test_stream_resilience.py --output",
    )
    parser.add_argument(
        "--require-log",
        action="append",
        default=[],
        help="Required test log path (repeat for each log file)",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resilience_path = Path(args.resilience_metrics)
    resilience = {}
    if _is_nonempty_file(resilience_path):
        resilience = json.loads(resilience_path.read_text(encoding="utf-8"))

    checks: list[dict[str, object]] = []
    required_logs = [Path(p) for p in args.require_log]
    for log_path in required_logs:
        checks.append(
            {
                "name": f"log:{log_path.name}",
                "path": str(log_path),
                "passed": _is_nonempty_file(log_path),
            }
        )
    checks.append(
        {
            "name": "stream_resilience_metrics",
            "path": str(resilience_path),
            "passed": bool(resilience.get("ok") and isinstance(resilience.get("health"), dict)),
            "health": resilience.get("health"),
        }
    )
    status = "passed" if all(bool(c["passed"]) for c in checks) else "failed"
    report = {
        "suite": "software_gate",
        "timestamp_unix": int(time.time()),
        "host_platform": platform.platform(),
        "checks": checks,
        "status": status,
    }
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0 if status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
