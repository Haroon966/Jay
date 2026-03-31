/**
 * Jay – Audio task (I2S mic/speaker, codec, SPP bridge)
 */
#ifndef JAY_AUDIO_TASK_H
#define JAY_AUDIO_TASK_H

#include "app_config.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Start audio tasks: init I2S and codec, start capture/decode/playback loops.
 * Must call spp_task_start() with audio_task_spp_rx_cb and NULL before or after.
 * Returns 0 on success.
 */
int audio_task_start(void);

void audio_task_stop(void);

/**
 * SPP receive callback: queue payload for decode/playback task.
 * Keep callback work minimal; this runs in SPP callback context.
 */
void audio_task_spp_rx_cb(const uint8_t *payload, uint16_t payload_len, void *arg);

#ifdef __cplusplus
}
#endif

#endif /* JAY_AUDIO_TASK_H */
