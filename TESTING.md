# Jay – Testing

## Unit

- **Protocol**: Packet builder/parser. From repo root:
  ```bash
  python3 tests/test_packet_format.py
  ```
  Verifies: given N bytes payload, produce 2 + N bytes; parse back to N.

- **Codec**: Encode 20 ms of silence or tone; decode; compare length and basic validity (run on firmware/Android when Opus is integrated).

## Integration

- **ESP32 ↔ ESP32**: Two dev boards, same firmware; connect and talk (after wiring mic/speaker).
- **ESP32 ↔ Android**: One helmet (or dev board) and one phone; pair if needed, then connect. Voice both ways (use same codec: Opus on both for interop).
- **Android ↔ Android**: Two phones; start intercom on both; connect and talk.
- **Desktop ↔ ESP32/Android**: Run `desktop/linux/intercom_spp_client.py <BDADDR>`; ensure packet exchange matches protocol.

## E2E and Hardware

- Two helmets in range: power on both, verify auto-connect and voice both ways.
- Walk out of range: verify disconnect; walk back: verify reconnect (if implemented).
- Battery life: run for 1–2 hours and confirm acceptable drain.

## Latency

- Measure: mic capture → encode → SPP → decode → play. Target < 200 ms end-to-end; tune frame size and buffers.
