/**
 * Jay – Firmware config (sync with protocol/constants.h)
 */
#ifndef JAY_APP_CONFIG_H
#define JAY_APP_CONFIG_H

/* Protocol constants (must match protocol/constants.h) */
#define INTERCOM_SPP_SERVICE_UUID_STR "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
#define INTERCOM_DEVICE_NAME_PREFIX   "Helmet-"
#define AUDIO_SAMPLE_RATE             16000
#define AUDIO_FRAME_MS                20
#define AUDIO_FRAME_SAMPLES           320
#define AUDIO_BYTES_PER_FRAME         640
#define CODEC_BITRATE                 16000
#define PACKET_HEADER_SIZE             2
#define MAX_PAYLOAD_LEN               512
#define INTERCOM_RSSI_THRESHOLD_DBM   (-70)

/* I2S pins (ESP32) */
#define I2S_BCK_GPIO    26
#define I2S_WS_GPIO     25
#define I2S_DO_GPIO     21   /* data out to speaker (TX) */
#define I2S_DI_GPIO     22   /* data in from mic (RX) */

#define SPP_SERVICE_NAME "Intercom"

#endif /* JAY_APP_CONFIG_H */
