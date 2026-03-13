# Jay

Bluetooth helmet-to-helmet (and device-to-device) voice intercom. Devices running this stack **auto-connect** when in range and support **full-duplex voice** with no internet or central server. Same protocol on **ESP32**, **Android**, **Desktop**, and (optionally) **iOS** (config only).

## Quick links

- **Protocol**: [protocol/SPEC.md](protocol/SPEC.md) – UUID, codec, packet format, state machine
- **Hardware**: [HARDWARE.md](HARDWARE.md) – BOM and wiring (ESP32 + INMP441 + MAX98357A)
- **Setup**: [SETUP.md](SETUP.md) – Tools and repo layout
- **Testing**: [TESTING.md](TESTING.md) – Unit, integration, E2E

## Building

| Component | How to build |
|-----------|----------------|
| **Firmware** | [firmware/README.md](firmware/README.md) – ESP-IDF: `idf.py set-target esp32 && idf.py build` |
| **Android** | Open [android/](android/) in Android Studio and run (min SDK 24, target 34) |
| **Desktop** | [desktop/README.md](desktop/README.md) – Linux Python script; Windows/macOS see platform READMEs |

## Protocol summary

- **Transport**: Bluetooth Classic SPP (RFCOMM). One bidirectional stream per connection.
- **Packet**: 2-byte length (little-endian) + payload. Payload = encoded audio (Opus 16 kHz, mono, 20 ms, 16 kbps) or future control.
- **Discovery**: SPP service. Android and desktop use standard SPP UUID `00001101-...` so they can connect to ESP32 (default SPP server). Device name prefix `Helmet-` for filtering.
- **1:1**: Each device runs one SPP server and can connect as client; one active voice peer.

## Repository layout

```
jay/
├── protocol/       # Spec, constants, packet parser
├── firmware/       # ESP32 (ESP-IDF, SPP, I2S, Opus)
├── android/        # Android app (Kotlin, SPP, audio, foreground service)
├── desktop/        # Linux / Windows / macOS clients
├── ios/            # Optional BLE companion (no voice)
└── tests/         # Unit tests (packet format)
```

## Future extensions

- **Multi-peer (1:many)**: One device to several peers; mix or choose one.
- **OTA**: Firmware update over BLE or Wi-Fi.
- **Noise suppression**: Speex DSP or RNNoise before encode.
- **Push-to-talk**: Optional mode to save battery.
