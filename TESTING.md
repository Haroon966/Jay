# Jay – Testing

## How to test (quick reference)

### 1. Unit test (no hardware)

From the project root:

```bash
cd /path/to/jay
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python3 tests/test_packet_format.py
python3 tests/test_constants_sync.py
python3 tests/test_stream_resilience.py --output artifacts/stream_resilience_metrics.json
```

You should see passing outputs (`test_packet_format OK`, `test_constants_sync OK`) and a JSON result from resilience checks. These cover packet framing, constants sync, and resilience budgets.

---

### 2. Android app (two phones, or one phone + ESP32)

**Two Android phones:**

1. Install the app on both phones. See [android/README.md](android/README.md): run from Android Studio over USB, build a debug APK and copy to the phone (or use `adb install`), or use wireless debugging.
2. **Pair the phones with each other (optional but helps):** Settings → Bluetooth → pair the other device. You can also pair phone ↔ ESP32 if testing with hardware.
3. On **Phone A**: Open Jay. After permissions are granted, the service auto-starts. The app becomes discoverable and listens for connections.
4. On **Phone B**: Open Jay. The service auto-starts and tries to connect to bonded devices whose name starts with `Helmet-`. If you didn’t set such a name, it will also accept an **incoming** connection from Phone A.
5. **Who connects to whom:** One phone’s SPP server accepts, the other’s client connects (e.g. after pairing, the client side connects to the server). If both only “wait”, ensure Bluetooth is on and try pairing first, then start intercom on both again.
6. When connected, speak on one phone; you should hear on the other. Android is Opus-first; if codec init fails, the app falls back to PCM passthrough.

**One phone + ESP32 (helmet):**

1. Flash the ESP32 firmware (see [firmware/README.md](firmware/README.md)). The device will advertise as `Helmet-ESP32`.
2. On the phone: Settings → Bluetooth → pair with `Helmet-ESP32`.
3. Open Jay. The service auto-starts and connects to the bonded `Helmet-*` device.
4. Talk: voice goes over SPP. Android and ESP32 should both use Opus for full interop; PCM fallback is only for degraded operation.

---

### 3. Desktop client (Linux, with PyBluez)

Useful to test SPP and packet exchange with a phone or ESP32.

**Install PyBluez (Debian/Ubuntu):**

Preferred — use the system package (avoids pip “externally-managed-environment” on Ubuntu 24.04+):

```bash
sudo apt update
sudo apt install python3-bluez
```

If that package is not available, use a virtual environment and pip:

```bash
cd jay/desktop/linux
python3 -m venv venv
source venv/bin/activate
sudo apt install python3-dev libbluetooth-dev
pip install pybluez
# Run the script with: python intercom_spp_client.py AA:BB:CC:DD:EE:FF
```

**Run the client:** Find the other device's Bluetooth address (e.g. Android: Settings → About → Bluetooth address; or `bluetoothctl` / `hcitool scan` on Linux). Then:

```bash
cd jay/desktop/linux
python3 intercom_spp_client.py AA:BB:CC:DD:EE:FF
```

Replace `AA:BB:CC:DD:EE:FF` with the actual device address. The script connects over SPP and sends/receives packets (no audio capture/playback in the script; it mainly tests the connection and packet format).

---

### 3b. Phone browser + desktop (no app on phone)

**Phone + desktop only** (no Bluetooth, no second device): Run `python3 intercom_web_bridge.py` or `python3 intercom_web_bridge.py --local` (no BDADDR). Install `sounddevice` and `libportaudio2` for desktop audio. Open the printed URL on your phone’s browser → Start voice. Your phone mic is heard on the desktop; desktop mic is heard on the phone. No app, no Bluetooth. **On the phone, the browser often blocks the microphone on plain http://.** Run with `--https` (and `pip install pyopenssl`), then open `https://<DESKTOP_IP>:8765` on the phone and accept the certificate warning so the mic is allowed.

**Test without a phone (desktop browser):** With the bridge running, on the **same machine** open `http://127.0.0.1:8765` (or `https://127.0.0.1:8765` if you used `--https`) in Chrome/Firefox. Allow the mic, tap **Start voice**. You should see "Voice on"; the desktop mic is played back in the browser. To check the server is up: `curl -k https://127.0.0.1:8765/ping` or `curl http://127.0.0.1:8765/ping` should return `ok`.

**Test from phone via ngrok (no same WiFi needed):** Run the bridge normally (e.g. `python3 intercom_web_bridge.py` without `--https`). In **another terminal** run: `ngrok http 8765` ([ngrok.com](https://ngrok.com), free tier). Ngrok will print a public **https** URL (e.g. `https://abc123.ngrok-free.app`). Open that URL on your phone’s browser (phone can be on mobile data or any WiFi). The browser gets real HTTPS so the microphone is allowed; traffic is tunneled to your desktop. WebSockets work through ngrok. **Localtunnel:** If you use `npx localtunnel --port 8765`, when you open the URL on your phone you may see a "tunnel password" page—enter the **IP address** shown on that page in the box, then continue. **If you try localtunnel** (`npx localtunnel --port 8765`) and get “connection refused: localtunnel.me” or similar, your network or firewall is likely blocking outbound connections to the tunnel server; use ngrok instead (or test from the desktop browser / same WiFi).

**Bridge to Bluetooth device** (ESP32 or another phone with Jay): Use the desktop as a Bluetooth bridge: desktop connects to the other device over SPP (the other device can be an ESP32 with Jay firmware or another phone with the Jay app; you do **not** need the app on this phone — only a browser).  you open a web page on your phone’s browser and talk through the desktop.

1. **On the desktop (Linux):** Install deps and run the web bridge (phone and desktop must be on the same WiFi). From the **jay** project root:
   - Bluetooth (system): `sudo apt install python3-bluez`
   - Flask in a venv that can see system packages (so the venv sees `bluetooth`). Run **either** from `desktop/linux` or from jay root using the script path:
     ```bash
     cd desktop/linux
     python3 -m venv --system-site-packages venv
     source venv/bin/activate
     pip install flask flask-sock sounddevice
     python3 intercom_web_bridge.py AA:BB:CC:DD:EE:FF
     ```
     If you created the venv in the jay root instead, run: `python3 desktop/linux/intercom_web_bridge.py AA:BB:CC:DD:EE:FF`
   Use the Bluetooth address of the device running SPP (e.g. the ESP32), not the phone you're browsing from. The script prints something like: `Open on your phone: http://192.168.1.10:8765`
2. **On the phone:** In the browser, open that URL (e.g. `http://192.168.1.10:8765`). Allow microphone when prompted, tap **Start voice**. Your voice goes: phone mic → browser → desktop (WiFi) → Bluetooth SPP → other device; the other side’s voice comes back the same way.

   **If you get “Connection refused”:** The device you’re connecting to (the other phone or ESP32) must have the SPP server running and be paired with the desktop. For a phone: open the Jay app and tap **Start Intercom** on that phone first, then run the bridge on the desktop.

---

### 4. ESP32 ↔ ESP32 (two boards with mic/speaker)

1. Wire two ESP32s with I2S mic (e.g. INMP441) and speaker (e.g. MAX98357A) as in [HARDWARE.md](HARDWARE.md).
2. Flash the same firmware on both.
3. Power both on; one will discover the other (name `Helmet-ESP32`) and connect via SPP.
4. Talk into one board’s mic; you should hear on the other’s speaker.

---

## Unit

- **Protocol**: Packet builder/parser. From repo root:
  ```bash
  python3 tests/test_packet_format.py
  ```
  Verifies: given N bytes payload, produce 2 + N bytes; parse back to N.

- **Codec**: Encode 20 ms of silence or tone; decode; compare length and basic validity (Opus is integrated on firmware and Android).

## Integration

- **ESP32 ↔ ESP32**: Two dev boards, same firmware; connect and talk (after wiring mic/speaker).
- **ESP32 ↔ Android**: One helmet (or dev board) and one phone; pair if needed, then connect. Voice both ways (use same codec: Opus on both for interop).
- **Android ↔ Android**: Two phones; start intercom on both; connect and talk.
- **Desktop ↔ ESP32/Android**: Run `desktop/linux/intercom_spp_client.py <BDADDR>`; ensure packet exchange matches protocol.

## Reliability checks (intercom-focused)

Run these after any transport/state-machine change:

- **Reconnect stability**: power-cycle one side 5 times; verify the other side returns to scan/idle and reconnects without app restart.
- **No-interaction startup**: relaunch Android after first permission grant and verify service/connect loop starts without tapping Start.
- **Malformed packet resilience**: inject bad length frames from desktop script; verify receiver drops bad frames and keeps session alive.
- **Session churn**: perform 20 connect/disconnect cycles (manual or scripted) and confirm no crash, stuck state, or resource leak.
- **Bonded-peer priority**: with 2+ discoverable devices, confirm connection chooses bonded `Helmet-*` peer first.

## E2E and Hardware

- Two helmets in range: power on both, verify auto-connect and voice both ways.
- Walk out of range: verify disconnect; walk back: verify reconnect (if implemented).
- Battery life: run for 1–2 hours and confirm acceptable drain.
- Noisy ride simulation (fan/wind noise near mic): verify speech remains intelligible and duplex stays stable.

## Multi-peer roadmap validation (planned)

For future `1:many` support, keep validation phased:

1. **Relay phase**: one uplink source and two listeners, no mixing.
2. **Selective route phase**: choose active talker/listener path from app control.
3. **Mixing phase**: optional low-count mixing with latency and clipping checks.

## Latency

- Measure: mic capture → encode → SPP → decode → play. Target < 200 ms end-to-end; tune frame size and buffers.

### Performance budget (release gate)

- **Latency budget**: p50 <= 140 ms, p95 <= 220 ms (representative indoor test path).
- **Queue budget**: playback queue depth <= 6 frames, TX queue depth <= 6 frames during steady-state talk.
- **Parser budget**: malformed frame handling must keep session alive; parser error count <= 5 per 10k frames in stress tests.
- **Drop budget**: dropped packets <= 20 per 10k frames in software soak (no active RF interference injection).
- **Recovery budget**: return to `IDLE` <= 1 s after disconnect, reconnect attempts use bounded backoff (1 s -> 12 s cap).

---

## Mandatory pre-release gates

All protocol-affecting changes must pass these gates before merge:

1. `python3 tests/test_packet_format.py` passes.
2. `python3 tests/test_constants_sync.py` passes.
3. `python3 tests/test_stream_resilience.py` passes.
4. At least one software interop path passes (`Android <-> Desktop` or parser robustness checks).
5. Software soak metrics stay within budget (`play_queue_depth<=6`, `tx_queue_depth<=6`, `parser_errors<=5`, `packets_dropped<=20`, `reconnect_attempts<=3`).
6. At least one hardware interop path passes (`Android <-> ESP32`, `Desktop <-> ESP32`, or `ESP32 <-> ESP32`).
7. Reconnect churn test (20 connect/disconnect cycles) completes with no stuck state.
8. No crash/deadlock on malformed/invalid length packets.

## Interop matrix

| Path | Type | How to run | Pass criteria |
|------|------|------------|---------------|
| Protocol framing | Software | `python3 tests/test_packet_format.py` | All parser/build/stream reassembly cases pass |
| Constants sync | Software | `python3 tests/test_constants_sync.py` | Android and firmware constants match `protocol/constants.json` |
| Stream resilience | Software | `python3 tests/test_stream_resilience.py` | Burst parser/recovery checks pass and budgets validated |
| Android <-> Desktop | Software/manual | Run Android app + `desktop/linux/intercom_web_bridge.py` | Bidirectional voice, reconnect after link drop |
| Desktop parser robustness | Software/manual | Inject invalid frames via desktop scripts | Invalid frames dropped, session loop survives |
| Android <-> ESP32 | Hardware | Phone app with flashed ESP32 | Connect + 2-way audio + reconnect |
| Desktop <-> ESP32 | Hardware | `intercom_spp_client.py` + ESP32 | Stable framed packet exchange |
| ESP32 <-> ESP32 | Hardware | Two flashed boards | Auto-connect and speech path works |

## CI mapping

- `.github/workflows/ci.yml`: packet-format tests, constants-sync tests, Android build, and firmware build.
- `.github/workflows/interop-matrix.yml`: software gate (protocol + constants + resilience) with log/metrics artifacts and report status; hardware matrix via manual dispatch or nightly schedule on self-hosted runner.

### Hardware matrix evidence format

`tests/run_hardware_matrix_check.py` now requires an evidence JSON file passed via `--evidence`. Example:

```json
{
  "connectivity": true,
  "audio_bidir": true,
  "recovery": true,
  "malformed_resilience": true
}
```

If any key is false, the hardware gate returns non-zero and emits `status: failed`.

## Release checklist

- Protocol version and constants are aligned across Android, firmware, and desktop (source: `protocol/constants.json`).
- Relay mode limits (`--relay`, `--max-clients`) are documented and validated.
- Field/noise simulation check completed (fan/wind near mic).
- Rollback path: if release candidate regresses interop, revert protocol-affecting commits first and redeploy previous known-good binaries.
