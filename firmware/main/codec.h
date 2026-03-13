/**
 * Jay – Codec (Opus) encode/decode
 */
#ifndef JAY_CODEC_H
#define JAY_CODEC_H

#include "app_config.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Max encoded bytes per 20 ms frame at 16 kbps (~40 bytes) */
#define CODEC_MAX_FRAME_BYTES  128

/**
 * Initialize encoder and decoder. Call once at startup.
 * Returns 0 on success, -1 on error.
 */
int codec_init(void);

/**
 * Free encoder/decoder. Call on shutdown.
 */
void codec_deinit(void);

/**
 * Encode one frame of PCM (AUDIO_FRAME_SAMPLES samples = 20 ms).
 * pcm: 16-bit mono, AUDIO_FRAME_SAMPLES samples.
 * out: buffer of at least CODEC_MAX_FRAME_BYTES.
 * Returns encoded byte count, or negative on error.
 */
int codec_encode(const int16_t *pcm, uint8_t *out, size_t out_size);

/**
 * Decode one Opus frame into PCM.
 * in, in_len: encoded frame.
 * pcm: output buffer for AUDIO_FRAME_SAMPLES samples (16-bit mono).
 * Returns number of samples decoded, or negative on error.
 */
int codec_decode(const uint8_t *in, size_t in_len, int16_t *pcm);

#ifdef __cplusplus
}
#endif

#endif /* JAY_CODEC_H */
