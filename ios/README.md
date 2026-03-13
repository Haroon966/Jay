# Jay – iOS Companion (Optional)

**Scope**: No SPP voice on iOS. Use **BLE** for:

- Listing nearby helmets (by BLE name or custom GATT service)
- Reading/writing settings (e.g. volume, device name) if you add a GATT profile on ESP32
- Optional: firmware update (OTA) over BLE

**No voice**: Use Android or desktop for voice; iOS app is for setup only.

To implement: create an Xcode project, add CoreBluetooth, and implement a GATT client that discovers devices with a custom service UUID (to be defined when ESP32 BLE config is added).
