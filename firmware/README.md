# Jay – ESP32 Firmware

## Build

1. Install [ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/) v5.0+.
2. Source the environment: `. $IDF_PATH/export.sh` (or `source export.sh` on Windows).
3. From this directory run:
   ```bash
   idf.py set-target esp32
   idf.py build
   ```
4. Flash: `idf.py -p /dev/ttyUSB0 flash monitor` (adjust port).

## Dependencies

The project uses **esphome/micro-opus** for Opus codec. It is declared in `main/idf_component.yml`; the Component Manager will download it on first build. If the component name in `managed_components` differs (e.g. `micro_opus`), update `main/CMakeLists.txt` `REQUIRES` accordingly.

## Hardware

See [HARDWARE.md](../HARDWARE.md) for wiring (INMP441, MAX98357A, GPIOs).

## Protocol

See [protocol/SPEC.md](../protocol/SPEC.md). This firmware uses the same SPP service name and packet format (2-byte length + Opus payload).
