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
- **No-interaction reconnect**: Android, desktop bridge, desktop SPP client, and firmware keep retry loops active with bounded backoff (1 s -> 12 s cap) so links recover automatically after drops.
- **Constants source**: shared protocol values live in `protocol/constants.json`; Android and firmware constants must match.

## Repository layout

```
jay/
├── protocol/       # Spec, constants, packet parser
├── firmware/       # ESP32 (ESP-IDF, SPP, I2S, Opus)
├── android/        # Android app (Kotlin, SPP, audio, foreground service)
├── desktop/        # Linux / Windows / macOS clients
├── ios/            # Optional BLE companion (no voice)
├── tests/          # Protocol + resilience tests and gate report scripts
└── requirements-dev.txt  # Shared Python deps for desktop bridge tooling
```

## Future extensions

- **Multi-peer (1:many)**: One device to several peers; mix or choose one.
- **OTA**: Firmware update over BLE or Wi-Fi.
- **Noise suppression**: Speex DSP or RNNoise before encode.
- **Push-to-talk**: Optional mode to save battery.

## Reference repos: useful strengths

### [`luvinland/csr-bc05mm-intercom-for-motorcycle-helmet`](https://github.com/luvinland/csr-bc05mm-intercom-for-motorcycle-helmet)

- **Pro**: Feature-specific firmware modules (connection, stream control, event handlers, power/state managers) make embedded behavior easier to reason about and debug. **Adopt in Jay**: keep splitting firmware responsibilities into narrow modules (discovery, link policy, audio pipeline, power) with clear interfaces and test hooks.
- **Pro**: Event-driven state handling reflects a production intercom mindset (connect/reconnect/call/media transitions treated explicitly). **Adopt in Jay**: document and enforce a stricter shared state machine in `protocol/SPEC.md`, then mirror it in Android, desktop, and firmware implementations.
- **Pro**: Product-level concerns (battery, charger, LEDs/buttons, policy logic) are first-class, not afterthoughts. **Adopt in Jay**: prioritize a hardware behavior checklist and integration tests for battery/charging/indicator behavior alongside voice-path tests.
- **Pro**: Long-lived firmware structure shows maintainability patterns for Bluetooth Classic intercom products. **Adopt in Jay**: preserve backward-compatible packet and service behavior when adding features, and gate protocol changes behind explicit version notes.

### [`sutiialex/Motolky`](https://github.com/sutiialex/Motolky)

- **Pro**: Clear focus on noisy-environment group voice communication grounds design decisions in real rider/team usage. **Adopt in Jay**: prioritize DSP/noise-suppression tasks and field-test scenarios in helmet/bike conditions, not only desk tests.
- **Pro**: Android-first intercom framing lowers adoption friction for users with existing phones/headsets. **Adopt in Jay**: keep Android onboarding simple (permissions, pairing, one-tap start) and treat it as the fastest path for first-time validation.
- **Pro**: The project direction includes phone-mediated multi-device communication. **Adopt in Jay**: use this as validation for Jay's planned multi-peer work and define a phased `1:many` roadmap (single uplink relay first, then selective mix/routing).
- **Pro**: Practical app-level communication goals are balanced with lower-level audio/codec realities. **Adopt in Jay**: keep a strict boundary between transport/protocol and codec pipeline so integration work (Opus, bridging, platform ports) stays incremental.
