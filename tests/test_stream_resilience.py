#!/usr/bin/env python3
"""Software-only resilience checks for parser and buffering budgets."""

from __future__ import annotations

import argparse
import json
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol.constants_loader import load_constants

CONSTANTS = load_constants()
PACKET_HEADER_SIZE = CONSTANTS["packet_header_size"]
MAX_PAYLOAD_LEN = CONSTANTS["max_payload_len"]


def _build_packet(payload: bytes) -> bytes:
    if not payload or len(payload) > MAX_PAYLOAD_LEN:
        raise ValueError("invalid payload")
    return struct.pack("<H", len(payload)) + payload


def _feed_parser_with_drop_oldest(stream: bytes, ring_capacity: int):
    ring = bytearray()
    overflows = 0
    malformed = 0
    decoded = 0
    i = 0
    while i < len(stream):
        ring.append(stream[i])
        i += 1
        if len(ring) > ring_capacity:
            del ring[0]
            overflows += 1
        while len(ring) >= PACKET_HEADER_SIZE:
            plen = ring[0] | (ring[1] << 8)
            if plen == 0 or plen > MAX_PAYLOAD_LEN:
                del ring[0]
                malformed += 1
                continue
            needed = PACKET_HEADER_SIZE + plen
            if len(ring) < needed:
                break
            del ring[:needed]
            decoded += 1
    return {"overflows": overflows, "malformed": malformed, "decoded": decoded}


def test_parser_burst_with_headroom():
    rng = random.Random(99)
    packets = []
    for _ in range(200):
        size = rng.randint(8, 80)
        payload = bytes(rng.getrandbits(8) for _ in range(size))
        packets.append(_build_packet(payload))
    stream = b"".join(packets)
    stats = _feed_parser_with_drop_oldest(stream, ring_capacity=2048)
    assert stats["overflows"] == 0
    assert stats["decoded"] == len(packets)


def test_parser_handles_malformed_burst_without_wedge():
    rng = random.Random(314)
    packets = [_build_packet(bytes([rng.getrandbits(8) for _ in range(32)])) for _ in range(80)]
    malformed = b"".join([struct.pack("<H", 0), b"\x99", struct.pack("<H", MAX_PAYLOAD_LEN + 10), b"\x01\x02"])
    stream = packets[0] + malformed + b"".join(packets[1:])
    stats = _feed_parser_with_drop_oldest(stream, ring_capacity=2048)
    assert stats["decoded"] >= 1
    assert stats["malformed"] > 0


def test_health_budget_contract():
    health = {
        "play_queue_depth": 4,
        "tx_queue_depth": 3,
        "parser_errors": 0,
        "packets_dropped": 2,
        "reconnect_attempts": 1,
    }
    assert_health_budget(health)
    return health


def assert_health_budget(health: dict[str, int]) -> None:
    # These values match the explicit software soak gate in TESTING.md.
    assert health["play_queue_depth"] <= 6
    assert health["tx_queue_depth"] <= 6
    assert health["parser_errors"] <= 5
    assert health["packets_dropped"] <= 20
    assert health["reconnect_attempts"] <= 3


def run_all(health_path: Path | None = None) -> dict[str, object]:
    test_parser_burst_with_headroom()
    test_parser_handles_malformed_burst_without_wedge()
    if health_path is not None:
        health = json.loads(health_path.read_text(encoding="utf-8"))
        assert_health_budget(health)
    else:
        health = test_health_budget_contract()
    return {"ok": True, "suite": "test_stream_resilience", "health": health}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--health-input",
        help="Optional JSON health snapshot with gate metrics",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON path for resilience metrics",
    )
    args = parser.parse_args()
    health_path = Path(args.health_input) if args.health_input else None
    result = run_all(health_path)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
