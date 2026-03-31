#!/usr/bin/env python3
"""Unit tests for protocol framing (2-byte length LE + payload)."""
import random
import struct
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol.constants_loader import load_constants

CONSTANTS = load_constants()
PACKET_HEADER_SIZE = CONSTANTS["packet_header_size"]
MAX_PAYLOAD_LEN = CONSTANTS["max_payload_len"]


def build_packet(payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD_LEN:
        raise ValueError("payload too long")
    return struct.pack("<H", len(payload)) + payload


def read_packet(data: bytes):
    if len(data) < PACKET_HEADER_SIZE:
        return None, 0
    (plen,) = struct.unpack("<H", data[:PACKET_HEADER_SIZE])
    if plen == 0 or plen > MAX_PAYLOAD_LEN:
        return None, 0
    if len(data) < PACKET_HEADER_SIZE + plen:
        return None, 0
    return data[PACKET_HEADER_SIZE : PACKET_HEADER_SIZE + plen], PACKET_HEADER_SIZE + plen


def consume_stream_with_resync(data: bytes):
    """Consume a byte stream by dropping one byte on malformed headers."""
    buf = b""
    out = []
    i = 0
    while i < len(data):
        buf += bytes([data[i]])
        i += 1
        while True:
            if len(buf) < PACKET_HEADER_SIZE:
                break
            (plen,) = struct.unpack("<H", buf[:PACKET_HEADER_SIZE])
            if plen == 0 or plen > MAX_PAYLOAD_LEN:
                buf = buf[1:]
                continue
            needed = PACKET_HEADER_SIZE + plen
            if len(buf) < needed:
                break
            out.append(buf[PACKET_HEADER_SIZE:needed])
            buf = buf[needed:]
    return out


def test_build_and_read():
    payload = b"hello"
    pkt = build_packet(payload)
    assert pkt[0] == 5 and pkt[1] == 0
    out, consumed = read_packet(pkt)
    assert out == payload and consumed == 7

    payload2 = bytes(40)
    pkt2 = build_packet(payload2)
    out2, c2 = read_packet(pkt2)
    assert out2 == payload2 and c2 == 42

    # Need more data
    out3, c3 = read_packet(pkt + pkt[:3])
    assert out3 == payload and c3 == 7

def test_zero_length_rejected():
    pkt = struct.pack("<H", 0)
    out, consumed = read_packet(pkt)
    assert out is None and consumed == 0


def test_oversized_rejected():
    pkt = struct.pack("<H", MAX_PAYLOAD_LEN + 1) + b"a"
    out, consumed = read_packet(pkt)
    assert out is None and consumed == 0


def test_truncated_payload_rejected():
    pkt = struct.pack("<H", 8) + b"abcd"
    out, consumed = read_packet(pkt)
    assert out is None and consumed == 0


def test_concatenated_packets():
    p1 = build_packet(b"abc")
    p2 = build_packet(b"defgh")
    stream = p1 + p2

    out1, c1 = read_packet(stream)
    assert out1 == b"abc" and c1 == len(p1)

    out2, c2 = read_packet(stream[c1:])
    assert out2 == b"defgh" and c2 == len(p2)


def test_partial_stream_reassembly():
    packets = [build_packet(b"abc"), build_packet(bytes([1, 2, 3, 4, 5]))]
    stream = packets[0] + packets[1]
    buf = b""
    out = []

    for b in stream:
        buf += bytes([b])
        while True:
            payload, consumed = read_packet(buf)
            if payload is None:
                break
            out.append(payload)
            buf = buf[consumed:]

    assert out == [b"abc", bytes([1, 2, 3, 4, 5])]
    assert buf == b""


def test_random_roundtrip_samples():
    rng = random.Random(1337)
    for _ in range(200):
        size = rng.randint(1, MAX_PAYLOAD_LEN)
        payload = bytes(rng.getrandbits(8) for _ in range(size))
        pkt = build_packet(payload)
        parsed, consumed = read_packet(pkt)
        assert parsed == payload
        assert consumed == len(pkt)


def test_many_concatenated_packets():
    rng = random.Random(4242)
    payloads = []
    stream = b""
    for _ in range(75):
        size = rng.randint(1, 64)
        payload = bytes(rng.getrandbits(8) for _ in range(size))
        payloads.append(payload)
        stream += build_packet(payload)

    decoded = []
    idx = 0
    while idx < len(stream):
        payload, consumed = read_packet(stream[idx:])
        assert payload is not None
        decoded.append(payload)
        idx += consumed

    assert decoded == payloads


def test_parser_resync_after_malformed_headers():
    good = [build_packet(b"ok1"), build_packet(b"ok2")]
    # Single malformed byte between valid packets; parser should recover.
    stream = good[0] + b"\x00" + good[1]
    decoded = consume_stream_with_resync(stream)
    assert decoded == [b"ok1", b"ok2"]


def test_coalesced_burst_stream():
    rng = random.Random(2026)
    payloads = []
    chunks = []
    for _ in range(120):
        size = rng.randint(1, 96)
        payload = bytes(rng.getrandbits(8) for _ in range(size))
        payloads.append(payload)
        chunks.append(build_packet(payload))
    stream = b"".join(chunks)
    decoded = consume_stream_with_resync(stream)
    assert decoded == payloads


def test_parser_throughput_sanity():
    rng = random.Random(7)
    packets = []
    for _ in range(5000):
        size = rng.randint(8, 48)
        payload = bytes(rng.getrandbits(8) for _ in range(size))
        packets.append(build_packet(payload))
    stream = b"".join(packets)
    started = time.perf_counter()
    decoded = consume_stream_with_resync(stream)
    elapsed = time.perf_counter() - started
    assert len(decoded) == len(packets)
    # Generous budget: detects pathological O(n^2) parser regressions.
    assert elapsed < 2.0


def run_all():
    test_build_and_read()
    test_zero_length_rejected()
    test_oversized_rejected()
    test_truncated_payload_rejected()
    test_concatenated_packets()
    test_partial_stream_reassembly()
    test_random_roundtrip_samples()
    test_many_concatenated_packets()
    test_parser_resync_after_malformed_headers()
    test_coalesced_burst_stream()
    test_parser_throughput_sanity()
    print("test_packet_format OK")


if __name__ == "__main__":
    run_all()
