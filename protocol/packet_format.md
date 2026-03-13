# Packet Format – Binary Layout

## Wire Format (SPP stream)

All multi-byte integers are **little-endian**.

### Voice/audio packet

```
+--------+--------+------------------+
| len_lo | len_hi | payload (N bytes) |
+--------+--------+------------------+
  0        1       2 .. (2+N-1)
```

- **len_lo**, **len_hi**: Payload length N as 16-bit unsigned. `N = len_lo + (len_hi << 8)`.
- **payload**: N bytes of encoded audio (e.g. one Opus frame) or control (see below).

### Example: 20 ms Opus frame (N = 40)

Hex stream (conceptual):

```
28 00  [40 bytes of Opus data...]
```

- `0x28 0x00` → N = 40.

### Control packets (future)

If N ≥ 1 and first byte of payload is `0x00`:

| First byte | Meaning    |
|------------|------------|
| 0x00       | Mute       |
| 0x01       | Unmute     |
| 0xFF       | Disconnect |

Remaining bytes in payload are reserved. Receiver may ignore or use for extended control.

### Parsing algorithm

1. Read exactly 2 bytes → `len_lo`, `len_hi`.
2. N = len_lo + (len_hi << 8). If N > MAX_PAYLOAD_LEN (e.g. 512), treat as protocol error (disconnect or skip).
3. Read exactly N bytes into payload buffer.
4. If N ≥ 1 and payload[0] == 0x00, handle control; else decode payload as audio and play.
5. Go to step 1.

### Sending

1. Encode 20 ms of PCM to Opus (or Speex) → `payload`, length N.
2. Write 2 bytes: N in little-endian (low byte first).
3. Write N bytes: payload.
4. Repeat.
