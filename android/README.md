# Jay – Android App

## Build

Open the `android/` folder in Android Studio and run the app (min SDK 24, target 34).

## Permissions

The app requests at runtime: BLUETOOTH_SCAN, BLUETOOTH_CONNECT, BLUETOOTH_ADVERTISE, RECORD_AUDIO, POST_NOTIFICATIONS (Android 13+). Grant all for intercom to work.

## Protocol

Uses standard SPP UUID `00001101-...` so the app can connect to ESP32 firmware (default SPP server). Packet format: 2-byte length (little-endian) + payload. See [protocol/SPEC.md](../protocol/SPEC.md).

## Codec

Current implementation uses **PCM passthrough** (640 bytes per 20 ms frame). For interop with ESP32 (Opus), add an Opus library (e.g. JNI libopus or Concentus) and use 16 kHz, mono, 20 ms, 16 kbps in `AudioPipeline`.
