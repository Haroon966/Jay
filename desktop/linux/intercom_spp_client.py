#!/usr/bin/env python3
"""
Jay – Linux SPP client (BlueZ).
Connects to a device running the intercom (ESP32 or Android) and exchanges
packets: 2-byte length (little-endian) + payload.

Usage:
  pip install pybluez  # or use system bluetooth (rfcomm)
  python3 intercom_spp_client.py [BDADDR]

If BDADDR is omitted, scans for devices with name starting with "Helmet-".
Requires: bluetooth stack, libopus for encode/decode (optional; can use PCM passthrough).
"""

import socket
import struct
import sys
import threading

# Protocol constants (match protocol/constants.h)
PACKET_HEADER_SIZE = 2
MAX_PAYLOAD_LEN = 512
SAMPLE_RATE = 16000
FRAME_SAMPLES = 320
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"  # standard SPP for ESP32


def read_packet(sock):
    """Read one packet: 2-byte length (LE) + payload."""
    header = sock.recv(PACKET_HEADER_SIZE)
    if len(header) < PACKET_HEADER_SIZE:
        return None
    (plen,) = struct.unpack("<H", header)
    if plen > MAX_PAYLOAD_LEN:
        return None
    payload = b""
    while len(payload) < plen:
        chunk = sock.recv(plen - len(payload))
        if not chunk:
            return None
        payload += chunk
    return payload


def send_packet(sock, payload):
    """Send one packet: 2-byte length (LE) + payload."""
    if len(payload) > MAX_PAYLOAD_LEN:
        return False
    sock.sendall(struct.pack("<H", len(payload)) + payload)
    return True


def main():
    bdaddr = sys.argv[1] if len(sys.argv) > 1 else None
    if not bdaddr:
        print("Usage: intercom_spp_client.py <BDADDR>")
        print("Example: intercom_spp_client.py AA:BB:CC:DD:EE:FF")
        print("Discover devices with: hcitool scan or bluetoothctl")
        sys.exit(1)

    try:
        import bluetooth
    except ImportError:
        print("Install PyBluez: pip install pybluez (or use socket with RFCOMM)")
        sys.exit(1)

    # PyBluez: create RFCOMM socket and connect to SPP service (channel 1 typical)
    sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    try:
        sock.connect((bdaddr, 1))
    except Exception as e:
        print("Connect failed:", e)
        print("Ensure the other device has SPP server running and is paired.")
        sys.exit(1)

    print("Connected. Send/receive packets (Ctrl+C to exit).")
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                p = read_packet(sock)
                if p is None:
                    break
                # Optional: decode Opus and play; here we just count
                pass
            except (BrokenPipeError, ConnectionResetError, OSError):
                break

    def writer():
        # Optional: capture audio, encode Opus, send_packet(sock, payload)
        while not stop.is_set():
            stop.wait(0.02)

    rt = threading.Thread(target=reader, daemon=True)
    rt.start()
    try:
        writer()
    except KeyboardInterrupt:
        pass
    stop.set()
    sock.close()
    print("Done.")


if __name__ == "__main__":
    main()
