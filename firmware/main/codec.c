/**
 * Jay – Opus codec (16 kHz, mono, 20 ms, 16 kbps)
 */
#include "codec.h"
#include "esp_log.h"
#include <opus.h>
#include <string.h>

static const char *TAG = "codec";

static OpusEncoder *enc = NULL;
static OpusDecoder *dec = NULL;

int codec_init(void)
{
    int err;
    enc = opus_encoder_create(AUDIO_SAMPLE_RATE, 1, OPUS_APPLICATION_VOIP, &err);
    if (err != OPUS_OK || enc == NULL) {
        ESP_LOGE(TAG, "opus_encoder_create failed: %s", opus_strerror(err));
        return -1;
    }
    opus_encoder_ctl(enc, OPUS_SET_BITRATE(CODEC_BITRATE));

    dec = opus_decoder_create(AUDIO_SAMPLE_RATE, 1, &err);
    if (err != OPUS_OK || dec == NULL) {
        ESP_LOGE(TAG, "opus_decoder_create failed: %s", opus_strerror(err));
        opus_encoder_destroy(enc);
        enc = NULL;
        return -1;
    }
    return 0;
}

void codec_deinit(void)
{
    if (enc) {
        opus_encoder_destroy(enc);
        enc = NULL;
    }
    if (dec) {
        opus_decoder_destroy(dec);
        dec = NULL;
    }
}

int codec_encode(const int16_t *pcm, uint8_t *out, size_t out_size)
{
    if (enc == NULL || pcm == NULL || out == NULL || out_size < CODEC_MAX_FRAME_BYTES)
        return -1;
    int n = opus_encode(enc, pcm, AUDIO_FRAME_SAMPLES, out, (opus_int32)out_size);
    return n;
}

int codec_decode(const uint8_t *in, size_t in_len, int16_t *pcm)
{
    if (dec == NULL || in == NULL || pcm == NULL)
        return -1;
    int n = opus_decode(dec, in, (opus_int32)in_len, pcm, AUDIO_FRAME_SAMPLES, 0);
    return n;
}
