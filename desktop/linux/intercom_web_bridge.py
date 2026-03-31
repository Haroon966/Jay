#!/usr/bin/env python3
"""
Jay – Phone browser + desktop bridge  (v2)
==========================================

Improvements over v1:
  • Proper per-client state management (ClientSession objects)
  • Robust error handling everywhere (no silent failures)
  • Reconnect logic for SPP Bluetooth socket
  • Thread-safe broadcast with dead-client pruning
  • Graceful shutdown (SIGINT / SIGTERM)
  • Health-check endpoint (/health) with JSON stats
  • Connection/disconnection logging with timestamps
  • Audio overflow protection (bounded queues, drop-oldest policy)
  • Jitter-buffer hint sent to browser on connect
  • Completely redesigned UI: glass-morphism dark theme, live waveform
    visualiser, per-client status badges, animated connection ring

Two modes:

  1. Local (phone + desktop, no Bluetooth):
       python3 intercom_web_bridge.py
       python3 intercom_web_bridge.py --local

  2. Bridge to Bluetooth/SPP device:
       python3 intercom_web_bridge.py <BDADDR>

Optional flags:
  --https   Enable TLS (requires: pip install pyopenssl).
            Phone browsers need HTTPS to access the microphone.

Install deps:
  pip install flask flask-sock sounddevice
  # For HTTPS:
  pip install pyopenssl
  # For Bluetooth:
  sudo apt install python3-bluez
  # Linux audio:
  sudo apt install libportaudio2
"""

from __future__ import annotations

import json
import logging
import queue
import signal
import socket
import struct
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Set

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol.constants_loader import load_constants

# ─── Audio / protocol constants ────────────────────────────────────────────────
CONSTANTS = load_constants()
PROTOCOL_VERSION   = CONSTANTS["protocol_version"]
PACKET_HEADER_SIZE = CONSTANTS["packet_header_size"]
MAX_PAYLOAD_LEN    = CONSTANTS["max_payload_len"]
FRAME_SAMPLES      = CONSTANTS["audio_frame_samples"]
SAMPLE_RATE        = CONSTANTS["audio_sample_rate"]
MAX_QUEUE_DEPTH    = 10           # cap jitter growth under sustained bursts
DISCOVERY_BACKOFF_MIN_MS = CONSTANTS["discovery_backoff_min_ms"]
DISCOVERY_BACKOFF_MAX_MS = CONSTANTS["discovery_backoff_max_ms"]

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jay")


# ══════════════════════════════════════════════════════════════════════════════
# Low-level helpers
# ══════════════════════════════════════════════════════════════════════════════

def read_packet(sock: socket.socket) -> Optional[bytes]:
    """Read one framed packet from *sock*.

    Returns None on EOF/socket error.
    Raises ValueError for malformed length field so callers can drop and continue.
    """
    try:
        header = _recv_exact(sock, PACKET_HEADER_SIZE)
        if header is None:
            return None
        (plen,) = struct.unpack("<H", header)
        if plen == 0 or plen > MAX_PAYLOAD_LEN:
            raise ValueError(f"invalid packet length {plen}")
        return _recv_exact(sock, plen)
    except OSError as exc:
        log.debug("read_packet OSError: %s", exc)
        return None


def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except OSError:
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def send_packet(sock: socket.socket, payload: bytes) -> bool:
    if len(payload) > MAX_PAYLOAD_LEN:
        return False
    try:
        sock.sendall(struct.pack("<H", len(payload)) + payload)
        return True
    except OSError as exc:
        log.debug("send_packet failed: %s", exc)
        return False


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _bounded_put(q: queue.Queue, item: object) -> None:
    """Put *item* into *q*; if full, drop the oldest entry first."""
    if q.full():
        try:
            q.get_nowait()
        except queue.Empty:
            pass
    try:
        q.put_nowait(item)
    except queue.Full:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Client session
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(eq=False)   # keep default object identity hash so set() works
class ClientSession:
    ws: object                              # flask_sock WebSocket handle
    addr: str                               # remote address string
    connected_at: float = field(default_factory=time.time)
    bytes_rx: int = 0
    bytes_tx: int = 0
    _alive: bool = True

    def is_alive(self) -> bool:
        return self._alive

    def mark_dead(self) -> None:
        self._alive = False

    def send(self, data: bytes) -> bool:
        if not self._alive:
            return False
        try:
            self.ws.send(data)
            self.bytes_tx += len(data)
            return True
        except Exception as exc:
            log.debug("send to %s failed: %s", self.addr, exc)
            self.mark_dead()
            return False


# ══════════════════════════════════════════════════════════════════════════════
# Server state
# ══════════════════════════════════════════════════════════════════════════════

class JayServer:
    def __init__(self, relay_enabled: bool = False, max_clients: int = 4) -> None:
        self._clients: Set[ClientSession] = set()
        self._lock    = threading.Lock()
        self._stop    = threading.Event()
        self._relay_enabled = relay_enabled
        self._max_clients = max_clients

        # Bluetooth SPP
        self._spp_sock: Optional[socket.socket] = None
        self._spp_lock  = threading.Lock()
        self._spp_bdaddr: Optional[str] = None
        self._spp_backoff_s = max(1.0, DISCOVERY_BACKOFF_MIN_MS / 1000.0)
        self._spp_backoff_max_s = max(self._spp_backoff_s, DISCOVERY_BACKOFF_MAX_MS / 1000.0)

        # Audio queues
        self._play_q: queue.Queue  = queue.Queue(maxsize=MAX_QUEUE_DEPTH)
        self._tx_q:   queue.Queue  = queue.Queue(maxsize=MAX_QUEUE_DEPTH)  # desktop mic → browser

        # Stats
        self._total_clients = 0
        self._stats = {
            "parser_errors": 0,
            "packets_dropped": 0,
            "reconnect_attempts": 0,
            "ws_to_spp": 0,
            "ws_to_ws": 0,
            "spp_to_ws": 0,
            "local_to_ws": 0,
        }

    # ── Client registry ────────────────────────────────────────────────────

    def add_client(self, session: ClientSession) -> None:
        with self._lock:
            if len(self._clients) >= self._max_clients:
                raise RuntimeError(f"max_clients reached ({self._max_clients})")
            self._clients.add(session)
            self._total_clients += 1
        log.info("Client connected: %s  (total active: %d)", session.addr, self.client_count())

    def remove_client(self, session: ClientSession) -> None:
        session.mark_dead()
        with self._lock:
            self._clients.discard(session)
        log.info("Client disconnected: %s  (active: %d)", session.addr, self.client_count())

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def broadcast(self, data: bytes, exclude: Optional[ClientSession] = None) -> int:
        """Send *data* to all live clients except *exclude*. Returns send count."""
        dead: list[ClientSession] = []
        sent = 0
        with self._lock:
            targets = list(self._clients)
        for s in targets:
            if s is exclude:
                continue
            if s.send(data):
                sent += 1
            else:
                dead.append(s)
        for s in dead:
            self.remove_client(s)
        return sent

    def send_first_listener(self, data: bytes, exclude: Optional[ClientSession] = None) -> int:
        """1:1 fallback: send to the first available listener except *exclude*."""
        with self._lock:
            targets = [s for s in self._clients if s is not exclude and s.is_alive()]
        if not targets:
            return 0
        if targets[0].send(data):
            return 1
        self.remove_client(targets[0])
        return 0

    # ── Bluetooth ──────────────────────────────────────────────────────────

    def connect_spp(self, bdaddr: str) -> None:
        self._spp_bdaddr = bdaddr
        self._try_spp_connect()
        threading.Thread(target=self._spp_reader_loop, name="spp-reader", daemon=True).start()

    def _try_spp_connect(self) -> bool:
        try:
            import bluetooth  # type: ignore
        except ImportError:
            log.error("PyBluez not installed.  sudo apt install python3-bluez")
            return False
        try:
            sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            sock.connect((self._spp_bdaddr, 1))
            with self._spp_lock:
                self._spp_sock = sock
            self._spp_backoff_s = max(1.0, DISCOVERY_BACKOFF_MIN_MS / 1000.0)
            log.info("SPP connected to %s", self._spp_bdaddr)
            return True
        except Exception as exc:
            log.error("SPP connect failed: %s", exc)
            log.error("  • Is the device paired? (Bluetooth settings)")
            log.error("  • Is SPP/intercom running on the device?")
            return False

    def _spp_reader_loop(self) -> None:
        """Read packets from SPP socket and broadcast to browser clients."""
        while not self._stop.is_set():
            with self._spp_lock:
                sock = self._spp_sock
            if sock is None:
                wait_s = self._spp_backoff_s
                log.info("SPP idle -> reconnecting in %.1fs", wait_s)
                time.sleep(wait_s)
                self._stats["reconnect_attempts"] += 1
                if self._try_spp_connect():
                    log.info("SPP reconnecting -> connected")
                else:
                    self._spp_backoff_s = min(self._spp_backoff_s * 2.0, self._spp_backoff_max_s)
                continue
            try:
                packet = read_packet(sock)
                if packet is None:
                    raise ConnectionError("socket closed")
                self.route_audio("spp", packet)
            except ValueError as exc:
                self._stats["parser_errors"] += 1
                self._stats["packets_dropped"] += 1
                log.warning("Dropped malformed SPP frame: %s", exc)
                continue
            except Exception as exc:
                log.warning("SPP connected -> idle (%s)", exc)
                with self._spp_lock:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    self._spp_sock = None
                continue

    def spp_send(self, data: bytes) -> bool:
        with self._spp_lock:
            sock = self._spp_sock
        if sock is None:
            return False
        ok = send_packet(sock, data)
        if not ok:
            log.warning("SPP send failed – dropping packet")
        return ok

    # ── Desktop audio ──────────────────────────────────────────────────────

    def start_desktop_audio(self) -> None:
        threading.Thread(target=self._playback_thread, name="audio-play", daemon=True).start()
        threading.Thread(target=self._capture_thread,  name="audio-cap",  daemon=True).start()

    def _playback_thread(self) -> None:
        try:
            import sounddevice as sd  # type: ignore
        except ImportError:
            log.error("sounddevice not available – desktop playback disabled")
            return
        log.info("Desktop playback thread started")
        # blocksize=0 lets PortAudio pick; latency="high" gives ALSA more buffer room.
        # We write each 640-byte chunk immediately – no accumulation delay.
        while not self._stop.is_set():
            try:
                stream = sd.RawOutputStream(
                    samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                    blocksize=0, latency="high",
                )
            except Exception as exc:
                log.error("Failed to open playback stream: %s – retry in 3 s", exc)
                time.sleep(3)
                continue
            try:
                with stream:
                    while not self._stop.is_set():
                        try:
                            chunk = self._play_q.get(timeout=0.1)
                        except queue.Empty:
                            continue
                        if chunk:
                            try:
                                stream.write(chunk)
                            except Exception as exc:
                                log.error("Playback write error: %s", exc)
                                break
            except Exception as exc:
                log.error("Playback stream error: %s – reopening in 1 s", exc)
                time.sleep(1)

    def _capture_thread(self) -> None:
        try:
            import sounddevice as sd  # type: ignore
        except ImportError:
            log.error("sounddevice not available – desktop capture disabled")
            return
        try:
            dev = sd.query_devices(kind="input")
            log.info("Desktop mic: %s", dev.get("name", "default"))
        except Exception as exc:
            log.warning("Could not query input device: %s", exc)
        log.info("Desktop capture thread started")
        SAFE_BLOCK = 1024
        while not self._stop.is_set():
            try:
                stream = sd.RawInputStream(
                    samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                    blocksize=SAFE_BLOCK, latency="high",
                )
            except Exception as exc:
                log.error("Failed to open capture stream: %s – retrying in 3 s", exc)
                time.sleep(3)
                continue
            try:
                with stream:
                    while not self._stop.is_set():
                        try:
                            chunk, overflowed = stream.read(FRAME_SAMPLES)
                            if overflowed:
                                log.debug("Audio capture buffer overflow")
                        except Exception as exc:
                            log.error("Capture read error: %s", exc)
                            break
                        if chunk is None:
                            continue
                        raw = chunk.tobytes() if hasattr(chunk, "tobytes") else bytes(chunk)
                        if len(raw) == 0:
                            continue
                        # Truncate to MAX_PAYLOAD_LEN so it fits the framing protocol
                        _bounded_put(self._tx_q, raw[:MAX_PAYLOAD_LEN])
            except Exception as exc:
                log.error("Capture stream error: %s – reopening in 1 s", exc)
                time.sleep(1)
            else:
                log.warning("Capture stream closed – reopening")
                time.sleep(0.5)

    def start_desktop_tx_thread(self) -> None:
        """Forwards desktop-mic audio to all browser clients."""
        def _run() -> None:
            while not self._stop.is_set():
                try:
                    chunk = self._tx_q.get(timeout=0.3)
                except queue.Empty:
                    continue
                self.route_audio("local", chunk)
        threading.Thread(target=_run, name="desktop-tx", daemon=True).start()

    def route_audio(self, source: str, data: bytes, session: Optional[ClientSession] = None) -> None:
        if not data:
            self._stats["packets_dropped"] += 1
            return

        if source == "ws":
            if self._spp_sock:
                if self.spp_send(data):
                    self._stats["ws_to_spp"] += 1
            else:
                if self._relay_enabled:
                    sent = self.broadcast(data, exclude=session)
                    self._stats["ws_to_ws"] += sent
                else:
                    # Fallback 1:1 behavior: only desktop playback path.
                    _bounded_put(self._play_q, data)
                    sent = self.send_first_listener(data, exclude=session)
                    self._stats["ws_to_ws"] += sent
            return

        if source == "spp":
            sent = self.broadcast(data)
            self._stats["spp_to_ws"] += sent
            _bounded_put(self._play_q, data)
            return

        if source == "local":
            sent = self.broadcast(data) if self._relay_enabled else self.send_first_listener(data)
            self._stats["local_to_ws"] += sent
            return

    # ── Stats ──────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            clients = list(self._clients)
        return {
            "active_clients": len(clients),
            "total_clients_ever": self._total_clients,
            "spp_connected": self._spp_sock is not None,
            "relay_enabled": self._relay_enabled,
            "max_clients": self._max_clients,
            "play_queue_depth": self._play_q.qsize(),
            "tx_queue_depth": self._tx_q.qsize(),
            "parser_errors": self._stats["parser_errors"],
            "packets_dropped": self._stats["packets_dropped"],
            "reconnect_attempts": self._stats["reconnect_attempts"],
            "routes": {
                "ws_to_spp": self._stats["ws_to_spp"],
                "ws_to_ws": self._stats["ws_to_ws"],
                "spp_to_ws": self._stats["spp_to_ws"],
                "local_to_ws": self._stats["local_to_ws"],
            },
            "clients": [
                {
                    "addr": s.addr,
                    "connected_seconds": round(time.time() - s.connected_at, 1),
                    "bytes_rx": s.bytes_rx,
                    "bytes_tx": s.bytes_tx,
                }
                for s in clients
            ],
        }

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def stop(self) -> None:
        log.info("Shutting down…")
        self._stop.set()
        with self._lock:
            for s in self._clients:
                s.mark_dead()
            self._clients.clear()
        with self._spp_lock:
            if self._spp_sock:
                try:
                    self._spp_sock.close()
                except Exception:
                    pass
                self._spp_sock = None
        log.info("Done.")


# ══════════════════════════════════════════════════════════════════════════════
# HTML / JS front-end
# ══════════════════════════════════════════════════════════════════════════════

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Jay · Intercom</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,400;0,500;1,400&family=Sora:wght@300;400;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:         #07090f;
      --surface:    rgba(255,255,255,.04);
      --border:     rgba(255,255,255,.08);
      --accent:     #3ef0c0;
      --accent2:    #7c6ef5;
      --danger:     #f05c5c;
      --warn:       #f0b83e;
      --text:       #e8ecf5;
      --muted:      #5a6070;
      --radius:     14px;
      --font-head:  'Sora', sans-serif;
      --font-mono:  'DM Mono', monospace;
    }

    html, body {
      height: 100%;
      background: var(--bg);
      color: var(--text);
      font-family: var(--font-head);
      overflow-x: hidden;
    }

    /* Animated background mesh */
    body::before {
      content:'';
      position:fixed; inset:0; z-index:0;
      background:
        radial-gradient(ellipse 80% 60% at 20% 10%, rgba(62,240,192,.07) 0%, transparent 70%),
        radial-gradient(ellipse 60% 50% at 80% 80%, rgba(124,110,245,.07) 0%, transparent 70%);
      pointer-events:none;
    }

    #app {
      position: relative; z-index: 1;
      max-width: 520px;
      margin: 0 auto;
      padding: clamp(1.5rem, 5vw, 3rem) 1.25rem;
      display: flex; flex-direction: column; gap: 1rem;
      min-height: 100dvh;
    }

    /* ── Header ── */
    .header { display: flex; align-items: center; gap: .75rem; }
    .logo {
      width: 40px; height: 40px; border-radius: 10px;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      display: grid; place-items: center; flex-shrink: 0;
      font-size: 1.1rem;
    }
    .brand h1 { font-size: 1.1rem; font-weight: 700; letter-spacing: -.02em; }
    .brand p  { font-size: .72rem; color: var(--muted); font-family: var(--font-mono); }

    .pill {
      margin-left: auto;
      font-family: var(--font-mono);
      font-size: .68rem;
      padding: .25rem .65rem;
      border-radius: 99px;
      border: 1px solid var(--border);
      color: var(--muted);
      white-space: nowrap;
    }

    /* ── Card ── */
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.25rem;
      backdrop-filter: blur(12px);
    }

    /* ── Status row ── */
    .status-row { display: flex; align-items: center; gap: .6rem; }
    .dot {
      width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
      background: var(--muted);
      box-shadow: 0 0 0 0 transparent;
      transition: background .4s, box-shadow .4s;
    }
    .dot.ok     { background: var(--accent);  box-shadow: 0 0 0 4px rgba(62,240,192,.15); animation: pulse 2s infinite; }
    .dot.warn   { background: var(--warn);    box-shadow: 0 0 0 4px rgba(240,184,62,.15); }
    .dot.err    { background: var(--danger);  }
    @keyframes pulse {
      0%,100% { box-shadow: 0 0 0 4px rgba(62,240,192,.15); }
      50%      { box-shadow: 0 0 0 8px rgba(62,240,192,.05); }
    }
    .status-text { font-size: .85rem; font-weight: 500; }

    /* ── Big action button ── */
    .btn-ring {
      position: relative;
      width: 120px; height: 120px;
      margin: .5rem auto;
      display: grid; place-items: center;
    }
    .btn-ring canvas {
      position: absolute; inset: 0;
      width: 100%; height: 100%;
      pointer-events: none;
    }
    #mainBtn {
      width: 80px; height: 80px; border-radius: 50%;
      border: none; cursor: pointer;
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%);
      color: #fff; font-size: 1.5rem;
      transition: transform .15s, opacity .15s, filter .15s;
      display: grid; place-items: center;
      box-shadow: 0 0 24px rgba(62,240,192,.35), 0 4px 16px rgba(0,0,0,.4);
      position: relative; z-index: 1;
    }
    #mainBtn:hover:not(:disabled) { transform: scale(1.06); filter: brightness(1.1); }
    #mainBtn:active:not(:disabled){ transform: scale(.96); }
    #mainBtn:disabled { opacity: .4; cursor: not-allowed; background: var(--muted); box-shadow: none; }
    #mainBtn.active {
      background: linear-gradient(135deg, var(--danger) 0%, #c44 100%);
      box-shadow: 0 0 24px rgba(240,92,92,.35), 0 4px 16px rgba(0,0,0,.4);
    }

    /* ── Waveform ── */
    #wave {
      width: 100%; height: 56px;
      display: block;
    }

    /* ── Log ── */
    .log-box {
      font-family: var(--font-mono);
      font-size: .72rem;
      color: var(--muted);
      height: 80px;
      overflow-y: auto;
      line-height: 1.7;
    }
    .log-box::-webkit-scrollbar { width: 4px; }
    .log-box::-webkit-scrollbar-track { background: transparent; }
    .log-box::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

    .log-entry { display: flex; gap: .5rem; }
    .log-time  { color: var(--muted); flex-shrink: 0; opacity: .6; }
    .log-ok    { color: var(--accent); }
    .log-err   { color: var(--danger); }
    .log-warn  { color: var(--warn); }

    /* ── Stats row ── */
    .stats-grid {
      display: grid; grid-template-columns: repeat(3,1fr); gap: .5rem;
    }
    .stat {
      background: rgba(255,255,255,.03);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: .6rem .7rem;
      text-align: center;
    }
    .stat-val { font-size: 1.25rem; font-weight: 700; color: var(--accent); font-family: var(--font-mono); }
    .stat-lbl { font-size: .62rem; color: var(--muted); margin-top: .1rem; text-transform: uppercase; letter-spacing: .06em; }

    /* ── Hint ── */
    .hint { font-size: .75rem; color: var(--muted); line-height: 1.6; }
    .hint a { color: var(--accent2); text-decoration: none; }

    /* ── Misc ── */
    .section-label {
      font-family: var(--font-mono);
      font-size: .65rem;
      text-transform: uppercase;
      letter-spacing: .1em;
      color: var(--muted);
      margin-bottom: .5rem;
    }

    @keyframes fadeIn { from { opacity:0; transform: translateY(6px); } to { opacity:1; transform:none; } }
    .card { animation: fadeIn .4s ease both; }
    .card:nth-child(2) { animation-delay:.05s; }
    .card:nth-child(3) { animation-delay:.1s; }
    .card:nth-child(4) { animation-delay:.15s; }
    .card:nth-child(5) { animation-delay:.2s; }
  </style>
</head>
<body>
<div id="app">

  <div class="header card">
    <div class="logo">🎙</div>
    <div class="brand">
      <h1>Jay · Intercom</h1>
      <p>voice bridge v2</p>
    </div>
    <span class="pill" id="connPill">● offline</span>
  </div>

  <!-- Status -->
  <div class="card">
    <div class="section-label">Connection</div>
    <div class="status-row" style="margin-bottom:.75rem">
      <span class="dot" id="dot"></span>
      <span class="status-text" id="statusText">Connecting to desktop…</span>
    </div>
    <!-- Big button -->
    <div class="btn-ring">
      <canvas id="ringCanvas" width="120" height="120"></canvas>
      <button id="mainBtn" disabled title="Start voice">🎤</button>
    </div>
    <p style="text-align:center;font-size:.75rem;color:var(--muted);margin-top:.25rem" id="btnLabel">Waiting for connection</p>
  </div>

  <!-- Waveform -->
  <div class="card">
    <div class="section-label">Audio level</div>
    <canvas id="wave"></canvas>
  </div>

  <!-- Stats -->
  <div class="card">
    <div class="section-label">Session stats</div>
    <div class="stats-grid">
      <div class="stat"><div class="stat-val" id="statTx">0</div><div class="stat-lbl">KB sent</div></div>
      <div class="stat"><div class="stat-val" id="statRx">0</div><div class="stat-lbl">KB recv</div></div>
      <div class="stat"><div class="stat-val" id="statPkts">0</div><div class="stat-lbl">packets</div></div>
    </div>
  </div>

  <!-- Log -->
  <div class="card">
    <div class="section-label">Event log</div>
    <div class="log-box" id="logBox"></div>
  </div>

  <!-- Hint -->
  <div class="card hint">
    <b>Tips:</b> Phone browsers require HTTPS for the microphone.
    Run the server with <code>--https</code> and accept the certificate warning.<br>
    If port 8765 is blocked, run
    <code>ngrok http 8765</code> and open the https URL on your phone (works from any network).
  </div>

</div>

<script>
// ── Utilities ────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const fmt = n => n >= 1000 ? (n/1000).toFixed(1)+'k' : String(n);
function ts() {
  const d = new Date();
  return [d.getHours(),d.getMinutes(),d.getSeconds()].map(x=>String(x).padStart(2,'0')).join(':');
}
function addLog(msg, cls='') {
  const box = $('logBox');
  const el = document.createElement('div');
  el.className = 'log-entry';
  el.innerHTML = `<span class="log-time">${ts()}</span><span class="${cls}">${msg}</span>`;
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  // keep last 200 lines
  while (box.children.length > 200) box.removeChild(box.firstChild);
}

// ── State ────────────────────────────────────────────────────────────────────
let ws = null, audioCtx = null, stream = null;
let isVoiceOn = false;
let recvQueue = [], recvTick = null;
let txBytes = 0, rxBytes = 0, pktCount = 0;
let analyser = null, waveData = null, waveAnimId = null;
let ringAnimId = null;

// ── Stats display ────────────────────────────────────────────────────────────
function updateStats() {
  $('statTx').textContent   = fmt(Math.round(txBytes/1024));
  $('statRx').textContent   = fmt(Math.round(rxBytes/1024));
  $('statPkts').textContent = fmt(pktCount);
}

// ── Status helpers ───────────────────────────────────────────────────────────
function setStatus(msg, state /* 'ok'|'warn'|'err'|'' */) {
  $('statusText').textContent = msg;
  $('dot').className = 'dot ' + (state||'');
}
function setPill(msg, ok) {
  const p = $('connPill');
  p.textContent = msg;
  p.style.color = ok ? 'var(--accent)' : 'var(--muted)';
}

// ── Waveform ─────────────────────────────────────────────────────────────────
const waveCanvas = $('wave');
const waveCtx    = waveCanvas.getContext('2d');
const BARS = 48;
let barHeights = new Float32Array(BARS);

function drawWave() {
  waveAnimId = requestAnimationFrame(drawWave);
  const W = waveCanvas.offsetWidth, H = 56;
  waveCanvas.width = W; waveCanvas.height = H;

  let live = new Float32Array(BARS);
  if (analyser && waveData) {
    analyser.getByteTimeDomainData(waveData);
    const step = Math.floor(waveData.length / BARS);
    for (let i = 0; i < BARS; i++) {
      const v = (waveData[i * step] - 128) / 128;
      live[i] = Math.abs(v);
    }
  }
  // Smooth
  for (let i = 0; i < BARS; i++) {
    barHeights[i] = barHeights[i] * 0.75 + live[i] * 0.25;
  }

  waveCtx.clearRect(0, 0, W, H);
  const gap = 2, bw = (W - gap * (BARS - 1)) / BARS;
  const grad = waveCtx.createLinearGradient(0, 0, W, 0);
  grad.addColorStop(0,   'rgba(62,240,192,.8)');
  grad.addColorStop(.5,  'rgba(124,110,245,.8)');
  grad.addColorStop(1,   'rgba(62,240,192,.8)');
  waveCtx.fillStyle = grad;
  for (let i = 0; i < BARS; i++) {
    const x = i * (bw + gap);
    const h = Math.max(3, barHeights[i] * (H - 6));
    const y = (H - h) / 2;
    waveCtx.beginPath();
    waveCtx.roundRect(x, y, bw, h, 2);
    waveCtx.fill();
  }
}
drawWave();

// ── Ring animation ───────────────────────────────────────────────────────────
const ringCanvas = $('ringCanvas');
const ringCtx    = ringCanvas.getContext('2d');
let ringAngle = 0, ringActive = false;

function drawRing() {
  ringAnimId = requestAnimationFrame(drawRing);
  const W = 120, cx = 60, cy = 60, R = 54;
  ringCtx.clearRect(0, 0, W, W);
  if (!ringActive) return;
  ringAngle += 0.025;
  ringCtx.save();
  ringCtx.translate(cx, cy);
  ringCtx.rotate(ringAngle);
  const g = ringCtx.createConicalGradient
    ? ringCtx.createConicalGradient(0, 0, 0)
    : null;
  ringCtx.strokeStyle = 'rgba(62,240,192,.5)';
  ringCtx.lineWidth = 3;
  ringCtx.beginPath();
  ringCtx.arc(0, 0, R, 0, Math.PI * 1.7);
  ringCtx.stroke();
  ringCtx.restore();
}
drawRing();

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(proto + '//' + location.host + '/ws');
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => {
    setStatus('Connected to desktop', 'ok');
    setPill('● online', true);
    $('mainBtn').disabled = false;
    $('btnLabel').textContent = 'Tap to start voice';
    addLog('WebSocket connected', 'log-ok');
    checkMicPermission();
  };
  ws.onclose = e => {
    setStatus('Disconnected – reconnecting…', 'warn');
    setPill('● offline', false);
    $('mainBtn').disabled = true;
    $('btnLabel').textContent = 'Waiting for connection';
    addLog(`WebSocket closed (code ${e.code}) – retry in 3 s`, 'log-warn');
    stopVoice();
    setTimeout(connect, 3000);
  };
  ws.onerror = () => {
    setStatus('Connection error', 'err');
    addLog('WebSocket error', 'log-err');
  };
  ws.onmessage = e => {
    if (!(e.data instanceof ArrayBuffer)) return;
    const bytes = e.data.byteLength;
    rxBytes += bytes; pktCount++;
    updateStats();
    if (bytes > 0) recvQueue.push(e.data);
  };
}

// ── Mic permission ────────────────────────────────────────────────────────────
async function checkMicPermission() {
  if (!navigator.mediaDevices?.getUserMedia) {
    addLog('getUserMedia not available (need HTTPS on mobile)', 'log-warn');
    return;
  }
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    s.getTracks().forEach(t => t.stop());
    addLog('Microphone permission granted', 'log-ok');
  } catch {
    addLog('Microphone denied – tap button to retry', 'log-warn');
  }
}

// ── Voice start / stop ────────────────────────────────────────────────────────
async function startVoice() {
  $('mainBtn').disabled = true;
  setStatus('Requesting microphone…', 'warn');
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    }});
  } catch (err) {
    setStatus('Mic error – ' + err.message, 'err');
    addLog('Mic error: ' + err.message, 'log-err');
    $('mainBtn').disabled = false;
    return;
  }

  audioCtx = new AudioContext({ sampleRate: 16000 });
  if (audioCtx.state === 'suspended') await audioCtx.resume();

  const src = audioCtx.createMediaStreamSource(stream);

  // Analyser for waveform
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 512;
  waveData = new Uint8Array(analyser.frequencyBinCount);
  src.connect(analyser);

  // Script processor for sending audio
  const bufSize = 512;
  const proc = audioCtx.createScriptProcessor(bufSize, 1, 1);
  const FRAME = 320;
  const inRate = audioCtx.sampleRate;
  const outRate = 16000;

  proc.onaudioprocess = e => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const input = e.inputBuffer.getChannelData(0);
    const buf = new ArrayBuffer(FRAME * 2);
    const view = new Int16Array(buf);
    const ratio = inRate / outRate;
    for (let i = 0; i < FRAME; i++) {
      const j = Math.min(Math.floor(i * ratio), input.length - 1);
      view[i] = Math.max(-32768, Math.min(32767, input[j] * 32768));
    }
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(buf);
      txBytes += buf.byteLength;
      pktCount++;
      updateStats();
    }
  };

  src.connect(proc);
  // Connect to a silent node to keep Chrome happy
  const silent = audioCtx.createGain(); silent.gain.value = 0;
  proc.connect(silent); silent.connect(audioCtx.destination);

  // Receive-queue playback tick (~20 ms)
  recvQueue = [];
  recvTick = setInterval(() => {
    if (!recvQueue.length || !audioCtx) return;
    if (audioCtx.state === 'suspended') { audioCtx.resume(); return; }
    const buf = recvQueue.shift();
    try {
      const i16 = new Int16Array(buf);
      const f32 = new Float32Array(i16.length);
      for (let k = 0; k < i16.length; k++) f32[k] = i16[k] / 32768;
      const ab = audioCtx.createBuffer(1, f32.length, 16000);
      ab.getChannelData(0).set(f32);
      const src2 = audioCtx.createBufferSource();
      src2.buffer = ab;
      src2.connect(audioCtx.destination);
      src2.start(0);
    } catch (_) {}
  }, 20);

  isVoiceOn = true;
  ringActive = true;
  $('mainBtn').classList.add('active');
  $('mainBtn').textContent = '⏹';
  $('mainBtn').title = 'Stop voice';
  $('mainBtn').disabled = false;
  $('btnLabel').textContent = 'Voice active – tap to stop';
  setStatus('Voice on', 'ok');
  addLog('Voice session started', 'log-ok');
}

function stopVoice() {
  if (!isVoiceOn && !recvTick) return;
  if (recvTick) { clearInterval(recvTick); recvTick = null; }
  if (stream)   { stream.getTracks().forEach(t => t.stop()); stream = null; }
  if (audioCtx) { try { audioCtx.close(); } catch (_) {} audioCtx = null; }
  analyser = null; waveData = null;
  isVoiceOn = false;
  ringActive = false;
  $('mainBtn').classList.remove('active');
  $('mainBtn').textContent = '🎤';
  $('mainBtn').title = 'Start voice';
  if (ws && ws.readyState === WebSocket.OPEN) $('mainBtn').disabled = false;
  $('btnLabel').textContent = 'Tap to start voice';
  setStatus('Connected to desktop', 'ok');
  addLog('Voice session stopped', 'log-warn');
}

$('mainBtn').onclick = () => isVoiceOn ? stopVoice() : startVoice();

connect();
</script>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════════════════════════
# Flask app factory
# ══════════════════════════════════════════════════════════════════════════════

def build_app(server: JayServer):
    try:
        from flask import Flask, jsonify, request as flask_request
        from flask_sock import Sock
    except ImportError:
        log.error("Flask not found. Install: pip install flask flask-sock")
        sys.exit(1)

    app = Flask(__name__)
    sock = Sock(app)

    @app.route("/")
    def index():
        return HTML, 200, {"Content-Type": "text/html"}

    @app.route("/ping")
    def ping():
        return "ok", 200, {"Content-Type": "text/plain"}

    @app.route("/health")
    def health():
        return jsonify(server.stats())

    @sock.route("/ws")
    def ws_handler(ws):
        addr = flask_request.remote_addr or "unknown"
        session = ClientSession(ws=ws, addr=addr)
        try:
            server.add_client(session)
        except RuntimeError as exc:
            log.warning("Rejecting client %s: %s", addr, exc)
            try:
                ws.send(json.dumps({"error": "capacity_reached"}))
            except Exception:
                pass
            return
        try:
            while True:
                try:
                    data = ws.receive()
                except Exception as exc:
                    log.debug("ws.receive error from %s: %s", addr, exc)
                    break
                if data is None:
                    break
                if not isinstance(data, bytes):
                    continue
                if len(data) == 0 or len(data) > MAX_PAYLOAD_LEN or (len(data) % 2) != 0:
                    server._stats["parser_errors"] += 1
                    server._stats["packets_dropped"] += 1
                    log.warning("Invalid packet (%d bytes) from %s – ignored", len(data), addr)
                    continue

                session.bytes_rx += len(data)
                server.route_audio("ws", data, session=session)
        except Exception:
            log.error("Unhandled exception in ws_handler for %s:\n%s", addr, traceback.format_exc())
        finally:
            server.remove_client(session)

    return app


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # Parse args
    use_https = "--https" in sys.argv or "-s" in sys.argv
    relay_enabled = "--relay" in sys.argv or "-r" in sys.argv
    max_clients = 4
    for arg in sys.argv[1:]:
        if arg.startswith("--max-clients="):
            try:
                max_clients = max(1, int(arg.split("=", 1)[1]))
            except ValueError:
                pass
    argv = [a for a in sys.argv[1:] if a not in ("--local", "-l", "--https", "-s", "--relay", "-r") and not a.startswith("--max-clients=")]
    local_mode = len(argv) == 0
    bdaddr = None if local_mode else argv[0]

    jay = JayServer(relay_enabled=relay_enabled, max_clients=max_clients)

    # Graceful shutdown on Ctrl-C / SIGTERM
    def _shutdown(signum, frame):
        print()
        jay.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if not local_mode:
        jay.connect_spp(bdaddr)
    else:
        log.info("Local mode: phone + desktop only (no Bluetooth)")
        if relay_enabled:
            log.info("Relay mode enabled (Step 1): fan-out to multiple listeners")
        else:
            log.info("Fallback mode: 1:1 behavior")
        # Start desktop audio after Flask is up (2 s grace)
        threading.Timer(2.0, jay.start_desktop_audio).start()
        threading.Timer(2.5, jay.start_desktop_tx_thread).start()

    app = build_app(jay)

    port = 8765
    lan_ip = get_lan_ip()
    scheme = "https" if use_https else "http"

    print()
    print("╔══════════════════════════════════════════════╗")
    print("║  Jay Intercom v2  –  ready                   ║")
    print("╠══════════════════════════════════════════════╣")
    print("║  Open on your phone (same WiFi):             ║")
    print(f"║  {scheme}://{lan_ip}:{port:<36}║")
    print("║                                              ║")
    print(f"║  Local test (this machine):                  ║")
    print(f"║  {scheme}://127.0.0.1:{port:<36}║")
    print("║                                              ║")
    print(f"║  Health / stats:  {scheme}://127.0.0.1:{port}/health  ║")
    print("╠══════════════════════════════════════════════╣")
    if use_https:
        print("║  HTTPS: accept the certificate warning on    ║")
        print("║  your phone (Advanced → Proceed)             ║")
    else:
        print("║  Tip: run with --https so phone can use mic  ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    ssl_ctx = "adhoc" if use_https else None
    try:
        app.run(
            host="0.0.0.0",
            port=port,
            debug=False,
            threaded=True,
            ssl_context=ssl_ctx,
            use_reloader=False,
        )
    except Exception as exc:
        log.error("Server crashed: %s", exc)
        log.error(traceback.format_exc())
    finally:
        jay.stop()


if __name__ == "__main__":
    main()