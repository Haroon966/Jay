/**
 * Jay – Shared protocol constants
 * Use in firmware and desktop; Android/iOS should match these values.
 */
#ifndef JAY_PROTOCOL_CONSTANTS_H
#define JAY_PROTOCOL_CONSTANTS_H

#ifdef __cplusplus
extern "C" {
#endif

/* SPP service UUID (string for Android/BlueZ; use same on ESP32 SDP) */
#define INTERCOM_PROTOCOL_VERSION  1
#define INTERCOM_SPP_SERVICE_UUID_STR "00001101-0000-1000-8000-00805F9B34FB"

/* Device name prefix for display and filtering */
#define INTERCOM_DEVICE_NAME_PREFIX "Helmet-"

/* Audio: 16 kHz, mono, 20 ms frame */
#define AUDIO_SAMPLE_RATE     16000
#define AUDIO_FRAME_MS        20
#define AUDIO_FRAME_SAMPLES   (AUDIO_SAMPLE_RATE * AUDIO_FRAME_MS / 1000)  /* 320 */
#define AUDIO_BYTES_PER_FRAME (AUDIO_FRAME_SAMPLES * 2)  /* 16-bit = 640 */

/* Codec */
#define CODEC_BITRATE         16000  /* 16 kbps */

/* Packet: 2-byte length (little-endian) + payload */
#define PACKET_HEADER_SIZE    2
#define MAX_PAYLOAD_LEN       512    /* sufficient for 20 ms Opus; protocol max 65535 */

/* Auto-connect: minimum RSSI (dBm) to consider peer "in range" */
#define INTERCOM_RSSI_THRESHOLD_DBM  (-70)
#define DISCOVERY_BACKOFF_MIN_MS     1000
#define DISCOVERY_BACKOFF_MAX_MS     12000

/* Control bytes (first byte of payload when present) */
#define INTERCOM_CTRL_MUTE        0x00
#define INTERCOM_CTRL_UNMUTE      0x01
#define INTERCOM_CTRL_DISCONNECT  0xFF

#ifdef __cplusplus
}
#endif

#endif /* JAY_PROTOCOL_CONSTANTS_H */
