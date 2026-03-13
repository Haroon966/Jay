# Jay – Protocol Specification

## 1. Transport and Discovery

- **Transport**: Bluetooth Classic **SPP (RFCOMM)**. One bidirectional byte stream per connection.
- **Service UUID**: All platforms must use the same UUID when registering or connecting to the SPP service.
  - **For ESP32 compatibility**: Use the standard SPP UUID `00001101-0000-1000-8000-00805F9B34FB` so that the ESP32 default SPP server (which does not support custom UUIDs in standard API) and Android/desktop clients can connect. Android and desktop implementations use this UUID.
  - **Optional (Android/desktop only)**: A custom UUID such as `a1b2c3d4-e5f6-7890-abcd-ef1234567890` can be used if only app-to-app or desktop-to-desktop connections are needed.
- **Device name**: Optional prefix for user display and filtering, e.g. `Helmet-` or `Intercom-` (e.g. `Helmet-A1B2`).

## 2. Codec and Audio Format

- **Codec**: **Opus** (recommended) or **Speex**.
  - **Opus**: 16 kHz, mono, 20 ms frame, application = `OPUS_APPLICATION_VOIP`, bitrate 16 kbps (CBR or constrained VBR). Max packet size ~40 bytes per 20 ms frame at 16 kbps.
  - **Speex**: 16 kHz, narrowband or wideband, 20 ms frame, bitrate ~15 kbps; similar packet sizing.
- **PCM (before encode)**: 16 kHz, mono, 16-bit signed linear. 20 ms = 320 samples = 640 bytes PCM.
- **Sample rate**: 16000 Hz (all platforms).
- **Frame duration**: 20 ms (configurable later to 40 ms if latency is acceptable for CPU trade-off).

## 3. Packet Format (Over SPP)

Every packet on the SPP stream:

| Offset | Size    | Description                                      |
|--------|---------|--------------------------------------------------|
| 0      | 2 bytes | Payload length N, **little-endian** 16-bit       |
| 2      | N bytes | Payload: encoded audio frame or control (see below) |

- **Length**: 16-bit unsigned. Max payload 65535 bytes.
- **Control (future)**: If first byte of payload is `0x00`, treat as control: e.g. `0x00` = mute, `0x01` = unmute, `0xFF` = disconnect. Otherwise entire payload is audio.
- **Framing**: Receiver reads 2 bytes (length), then N bytes (payload); repeat.

## 4. Connection Model (1:1)

- Each device runs **one SPP server** (acceptor) and can act as **one SPP client** (initiator).
- **1:1**: Only one active voice peer. If A’s client connects to B’s server, that is the single link; the other direction (B connecting to A) is not used for a second stream; one side accepts, one side initiates.
- **Auto-connect**: If not connected, scan for SPP service UUID; when a peer is found and optionally RSSI > threshold (e.g. -70 dBm), initiate SPP connection. Pair if not bonded (user may see pairing dialog once).

## 5. State Machine (Per Device)

| State      | Description                                                                 |
|------------|-----------------------------------------------------------------------------|
| **IDLE**   | Bluetooth on, discoverable, SPP server listening, not connected.           |
| **SCANNING** | Periodic or continuous scan for devices with our SPP service.              |
| **CONNECTING** | SPP client connect in progress, or incoming SPP accepted.              |
| **CONNECTED** | One SPP link up; bidirectional voice. On disconnect, return to IDLE/SCANNING. |

Bonding (“paired”) is stored at the stack level; when a bonded device is seen, CONNECTING can be automatic.

## 6. Constants Summary

- **AUDIO_SAMPLE_RATE**: 16000
- **AUDIO_FRAME_MS**: 20
- **AUDIO_FRAME_SAMPLES**: 320
- **CODEC_BITRATE**: 16000 (bps)
- **PACKET_HEADER_SIZE**: 2
- **MAX_PAYLOAD_LEN**: 512 (for voice frames; protocol allows up to 65535)
