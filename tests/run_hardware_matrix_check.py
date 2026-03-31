#!/usr/bin/env python3
"""Hardware-matrix harness entrypoint for self-hosted interop checks."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

VALID_PATHS = {"android-esp32", "desktop-esp32", "esp32-esp32"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True, choices=sorted(VALID_PATHS))
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--evidence",
        required=True,
        help="JSON file containing measured hardware check booleans/metrics",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path = Path(args.evidence)
    if not evidence_path.exists():
        raise FileNotFoundError(f"evidence file not found: {evidence_path}")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    expected = {
        "connectivity": bool(evidence.get("connectivity")),
        "audio_bidir": bool(evidence.get("audio_bidir")),
        "recovery": bool(evidence.get("recovery")),
        "malformed_resilience": bool(evidence.get("malformed_resilience")),
    }
    status = "passed" if all(expected.values()) else "failed"

    report = {
        "suite": "hardware_matrix",
        "path": args.path,
        "timestamp_unix": int(time.time()),
        "runner": os.environ.get("RUNNER_NAME", "unknown"),
        "instructions_ref": "TESTING.md#interop-matrix",
        "checks": {
            "connectivity": {
                "description": "connected session established",
                "passed": expected["connectivity"],
            },
            "audio_bidir": {
                "description": "bidirectional speech or packet flow",
                "passed": expected["audio_bidir"],
            },
            "recovery": {
                "description": "disconnect/reconnect passes",
                "passed": expected["recovery"],
            },
            "malformed_resilience": {
                "description": "invalid frames dropped without crash",
                "passed": expected["malformed_resilience"],
            },
        },
        "evidence_file": str(evidence_path),
        "status": status,
    }
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0 if status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
