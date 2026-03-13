#!/usr/bin/env python3
"""Unit test: packet format (2-byte length LE + payload)."""
import struct

PACKET_HEADER_SIZE = 2
MAX_PAYLOAD_LEN = 512


def build_packet(payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD_LEN:
        raise ValueError("payload too long")
    return struct.pack("<H", len(payload)) + payload


def read_packet(data: bytes):
    if len(data) < PACKET_HEADER_SIZE:
        return None, 0
    (plen,) = struct.unpack("<H", data[:PACKET_HEADER_SIZE])
    if plen > MAX_PAYLOAD_LEN:
        return None, 0
    if len(data) < PACKET_HEADER_SIZE + plen:
        return None, 0
    return data[PACKET_HEADER_SIZE : PACKET_HEADER_SIZE + plen], PACKET_HEADER_SIZE + plen


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

    print("test_packet_format OK")


if __name__ == "__main__":
    test_build_and_read()
