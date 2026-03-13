# Jay – Hardware (BOM and Wiring)

## 3.1 Components

| Item | Part / Example | Notes |
|------|----------------|--------|
| MCU | ESP32-WROOM-32 or ESP32-S3 | Dual-core helps: one for BT/SPP, one for codec/I2S. |
| Microphone | INMP441 (I2S digital) | 3.3 V, L/R to GND for left channel. |
| Speaker amp | MAX98357A (I2S in, speaker out) or PCM5102A + amp | 5 V for MAX98357A. |
| Battery | 3.7 V Li-ion + boost to 5 V or direct 3.3 V for ESP32 | Capacity depends on usage (e.g. 1000–2000 mAh). |
| Regulator | AMS1117-3.3 or similar | If battery > 3.3 V. |

## 3.2 Wiring (ESP32 + INMP441 + MAX98357A)

- **Shared I2S clock**: One I2S port, full-duplex (TX + RX).
  - **BCK (bit clock)**: e.g. GPIO 26 (shared).
  - **WS (LRCK)**: e.g. GPIO 25 (shared).
- **Microphone (RX)**:
  - **SD (data in)**: GPIO 22 or 34 (input).
  - INMP441: VDD→3.3 V, GND→GND, L/R→GND, SCK→GPIO 26, WS→GPIO 25, SD→GPIO 22.
- **Speaker (TX)**:
  - **DIN (data out)**: GPIO 21 (output). TX and RX use different data pins on same I2S port.
- **MAX98357A**: VIN→5 V, GND→GND, BCLK→GPIO 26, LRCK→GPIO 25, DIN→GPIO 21.

**Note**: On some boards TX and RX must use different data pins. Confirm from [ESP32 I2S docs](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/i2s.html).

## 3.3 Mechanical / Enclosure

- Mount ESP32, mic, and amp in a small enclosure; mic and speaker positioned for helmet (e.g. near mouth and ear). Consider wind/noise and future acoustic tuning.
