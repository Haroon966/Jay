#!/usr/bin/env python3
"""
Jay - Linux SPP client (BlueZ) with auto-reconnect.
Connects to a device running the intercom (ESP32 or Android) and exchanges
packets: 2-byte length (little-endian) + payload.

Usage:
  python3 intercom_spp_client.py [BDADDR]

If BDADDR is omitted, the client repeatedly scans for a device name starting
with the configured prefix and reconnects automatically after drops.
"""

import socket
import struct
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol.constants_loader import load_constants

# Protocol constants (loaded from protocol/constants.json)
CONSTANTS = load_constants()
PROTOCOL_VERSION = CONSTANTS["protocol_version"]
PACKET_HEADER_SIZE = CONSTANTS["packet_header_size"]
MAX_PAYLOAD_LEN = CONSTANTS["max_payload_len"]
SAMPLE_RATE = CONSTANTS["audio_sample_rate"]
FRAME_SAMPLES = CONSTANTS["audio_frame_samples"]
SPP_UUID = CONSTANTS["spp_service_uuid"]
DEVICE_NAME_PREFIX = CONSTANTS["device_name_prefix"]
DISCOVERY_BACKOFF_MIN_MS = CONSTANTS["discovery_backoff_min_ms"]
DISCOVERY_BACKOFF_MAX_MS = CONSTANTS["discovery_backoff_max_ms"]


def read_packet(sock):
    """Read one packet: 2-byte length (LE) + payload."""
    header = recv_exact(sock, PACKET_HEADER_SIZE)
    if not header:
        return None
    (plen,) = struct.unpack("<H", header)
    if plen == 0 or plen > MAX_PAYLOAD_LEN:
        return None
    return recv_exact(sock, plen)


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def send_packet(sock, payload):
    """Send one packet: 2-byte length (LE) + payload."""
    if len(payload) > MAX_PAYLOAD_LEN:
        return False
    sock.sendall(struct.pack("<H", len(payload)) + payload)
    return True


def discover_target_bda(bluetooth):
    """Return first discoverable address matching DEVICE_NAME_PREFIX."""
    try:
        nearby = bluetooth.discover_devices(duration=8, lookup_names=True)
    except Exception:
        return None
    for addr, name in nearby:
        if (name or "").startswith(DEVICE_NAME_PREFIX):
            return addr
    return None


def resolve_channel(bluetooth, bdaddr):
    try:
        services = bluetooth.find_service(uuid=SPP_UUID, address=bdaddr)
    except Exception:
        services = []
    return services[0]["port"] if services else 1


def run_session(bluetooth, bdaddr):
    channel = resolve_channel(bluetooth, bdaddr)
    sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    sock.connect((bdaddr, channel))
    print(f"Connected to {bdaddr} (channel {channel}).")
    stop = threading.Event()
    stats = {
        "rx_packets": 0,
        "rx_bytes": 0,
        "tx_packets": 0,
        "tx_bytes": 0,
        "started": time.time(),
    }

    def reader():
        while not stop.is_set():
            try:
                p = read_packet(sock)
                if p is None:
                    break
                stats["rx_packets"] += 1
                stats["rx_bytes"] += len(p)
            except (BrokenPipeError, ConnectionResetError, OSError):
                break
        stop.set()

    def writer():
        # Optional: capture audio, encode Opus, send_packet(sock, payload)
        while not stop.is_set():
            stop.wait(0.02)

    rt = threading.Thread(target=reader, daemon=True)
    rt.start()
    try:
        writer()
    finally:
        stop.set()
        try:
            sock.close()
        except Exception:
            pass

    elapsed = max(1.0, time.time() - stats["started"])
    print(
        "Session stats:",
        f"rx_packets={stats['rx_packets']}",
        f"rx_kbps={stats['rx_bytes'] * 8 / elapsed / 1000:.1f}",
        f"tx_packets={stats['tx_packets']}",
        f"tx_kbps={stats['tx_bytes'] * 8 / elapsed / 1000:.1f}",
    )


def main():
    bdaddr = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        import bluetooth
    except ImportError:
        print("PyBluez not found. On Debian/Ubuntu install the system package:")
        print("  sudo apt install python3-bluez")
        print("Or use a venv: python3 -m venv venv && source venv/bin/activate && pip install pybluez")
        sys.exit(1)

    print("SPP client running with auto-reconnect (Ctrl+C to exit).")
    backoff_ms = DISCOVERY_BACKOFF_MIN_MS
    try:
        while True:
            target = bdaddr
            if not target:
                print(f"Scanning for {DEVICE_NAME_PREFIX}* peers...")
                target = discover_target_bda(bluetooth)
                if not target:
                    print("No matching peer found. Retrying...")
                    time.sleep(backoff_ms / 1000.0)
                    backoff_ms = min(backoff_ms * 2, DISCOVERY_BACKOFF_MAX_MS)
                    continue
            try:
                run_session(bluetooth, target)
                backoff_ms = DISCOVERY_BACKOFF_MIN_MS
            except Exception as e:
                print("Connect/session failed:", e)
                print("Will retry with backoff.")
                time.sleep(backoff_ms / 1000.0)
                backoff_ms = min(backoff_ms * 2, DISCOVERY_BACKOFF_MAX_MS)
                if not bdaddr:
                    continue
    except KeyboardInterrupt:
        pass
    print("Done.")


if __name__ == "__main__":
    main()
