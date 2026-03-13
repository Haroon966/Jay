# Windows Desktop Client

Use WinRT `Windows.Devices.Bluetooth.Rfcomm.RfcommDeviceService` to connect to SPP by service UUID. Implement the same packet format (2-byte length + payload) and Opus encode/decode. Audio: WASAPI or DirectSound at 16 kHz mono 16-bit.

See [desktop/README.md](../README.md) and [protocol/SPEC.md](../../protocol/SPEC.md).
