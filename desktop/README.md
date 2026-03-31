# Jay – Desktop Client

Same protocol over SPP (2-byte length + payload, Opus or PCM). Use for testing or to talk from PC to helmet/phone.

## Linux (BlueZ)

- **Requirements**: Python 3.10+, `pybluez` or `bleak` (for BLE; for SPP use `bluetooth` module or `sdptool`/`rfcomm`).
- **SPP**: Register SPP service with standard UUID, or connect to a device running the intercom (e.g. `rfcomm connect /dev/rfcomm0 <bdaddr> 1`).
- **Recommended setup**:
  - `python3 -m venv desktop/linux/venv`
  - `source desktop/linux/venv/bin/activate`
  - `pip install -r requirements-dev.txt`
  - `sudo apt install python3-bluez libportaudio2` (system dependencies for Bluetooth/audio)
- **Scripts**:
  - `linux/intercom_spp_client.py` – minimal SPP client (connect by BDADDR; packet send/receive, no audio).
  - `linux/intercom_web_bridge.py` – **phone browser + desktop**: run on the desktop with a BDADDR; it starts a small web server. Open the printed URL on your phone’s browser (same WiFi) to use the intercom without installing the Android app. Requires `flask` and `flask-sock` (`pip install flask flask-sock`).

## Relay mode (multi-peer step 1)

`intercom_web_bridge.py` supports a phased step-1 relay mode:

- `--relay` / `-r`: fan-out one talker stream to multiple listeners (no mixing).
- `--max-clients=N`: admission limit for active browser listeners (default 4).
- Without `--relay`, fallback behavior stays near 1:1.

## Windows

- Use WinRT `Windows.Devices.Bluetooth.Rfcomm` to open SPP by service UUID. Same packet format and codec (e.g. libopus via ctypes or a C#/C++ helper).

## macOS

- Use IOBluetooth (Objective-C/Swift) to register SPP and connect. Same packet format and codec.

## Protocol

See [../protocol/SPEC.md](../protocol/SPEC.md). Audio: 16 kHz, mono, 20 ms frames; packet: 2 bytes length (LE) + payload.
