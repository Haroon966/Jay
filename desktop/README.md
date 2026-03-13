# Jay – Desktop Client

Same protocol over SPP (2-byte length + payload, Opus or PCM). Use for testing or to talk from PC to helmet/phone.

## Linux (BlueZ)

- **Requirements**: Python 3.10+, `pybluez` or `bleak` (for BLE; for SPP use `bluetooth` module or `sdptool`/`rfcomm`).
- **SPP**: Register SPP service with standard UUID, or connect to a device running the intercom (e.g. `rfcomm connect /dev/rfcomm0 <bdaddr> 1`).
- **Script**: See `linux/intercom_spp_client.py` for a minimal client that connects via RFCOMM and uses the same packet format.

## Windows

- Use WinRT `Windows.Devices.Bluetooth.Rfcomm` to open SPP by service UUID. Same packet format and codec (e.g. libopus via ctypes or a C#/C++ helper).

## macOS

- Use IOBluetooth (Objective-C/Swift) to register SPP and connect. Same packet format and codec.

## Protocol

See [../protocol/SPEC.md](../protocol/SPEC.md). Audio: 16 kHz, mono, 20 ms frames; packet: 2 bytes length (LE) + payload.
