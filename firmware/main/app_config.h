/**
 * Jay – Firmware config (sync with protocol/constants.json)
 */
#ifndef JAY_APP_CONFIG_H
#define JAY_APP_CONFIG_H

/* Protocol constants (must match protocol/SPEC.md, protocol/constants.json, and other platforms) */
#define INTERCOM_PROTOCOL_VERSION      1
#define INTERCOM_SPP_SERVICE_UUID_STR "00001101-0000-1000-8000-00805F9B34FB"
#define INTERCOM_DEVICE_NAME_PREFIX   "Helmet-"
#define AUDIO_SAMPLE_RATE             16000
#define AUDIO_FRAME_MS                20
#define AUDIO_FRAME_SAMPLES           320
#define AUDIO_BYTES_PER_FRAME         640
#define CODEC_BITRATE                 16000
#define PACKET_HEADER_SIZE             2
#define MAX_PAYLOAD_LEN               512
#define INTERCOM_RSSI_THRESHOLD_DBM   (-70)
#define DISCOVERY_BACKOFF_MIN_MS      1000
#define DISCOVERY_BACKOFF_MAX_MS      12000

/* I2S pins (ESP32) */
#define I2S_BCK_GPIO    26
#define I2S_WS_GPIO     25
#define I2S_DO_GPIO     21   /* data out to speaker (TX) */
#define I2S_DI_GPIO     22   /* data in from mic (RX) */

#define SPP_SERVICE_NAME "Intercom"

#endif /* JAY_APP_CONFIG_H */
