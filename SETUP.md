# Jay – Environment Setup

## Tools to Install

| Tool | Purpose | Where |
|------|--------|--------|
| **ESP-IDF** v5.0+ or **Arduino-ESP32** (ESP-IDF 5.x) | ESP32 build and flash | [ESP-IDF Get Started](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/) |
| **Android Studio** (Hedgehog 2023.1+) | Android app | SDK 24+ min, 34 target |
| **Git** | Version control | - |
| **Python 3.10+** (optional) | Desktop client or scripts | - |
| **BlueZ** (Linux) / **WinRT** (Windows) / **IOBluetooth** (macOS) | Desktop Bluetooth | OS-specific |

## Repository Layout

- **main** – stable releases
- **develop** – integration branch
- Optional feature branches: `firmware/`, `android/`, `desktop/`

## Quick Start

1. Clone or create repo: `jay/`
2. Read [protocol/SPEC.md](protocol/SPEC.md) for the protocol definition.
3. Build firmware: `cd firmware && idf.py build`
4. Build Android: open `android/` in Android Studio and run.
5. Desktop: see `desktop/README.md` per platform.
