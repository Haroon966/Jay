/**
 * Jay – SPP task (server + client, discovery, send/recv)
 */
#ifndef JAY_SPP_TASK_H
#define JAY_SPP_TASK_H

#include "app_config.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Callback when a packet (length + payload) is received. Called from SPP callback context; keep work minimal. */
typedef void (*spp_rx_cb_t)(const uint8_t *payload, uint16_t payload_len, void *arg);

/**
 * Start SPP task: init BT/SPP, start server, optionally run discovery and connect.
 * rx_cb and arg are passed to rx_cb when data is received.
 * Returns 0 on success.
 */
int spp_task_start(spp_rx_cb_t rx_cb, void *arg);

/**
 * Stop SPP task and disconnect.
 */
void spp_task_stop(void);

/**
 * Send one packet (2-byte length + payload). Thread-safe.
 * Non-blocking enqueue for low-latency audio paths.
 * Returns 0 on success, -1 if not connected or queue full/error.
 */
int spp_task_send(const uint8_t *payload, uint16_t payload_len);

/**
 * Return 1 if connected, 0 otherwise.
 */
int spp_task_is_connected(void);

#ifdef __cplusplus
}
#endif

#endif /* JAY_SPP_TASK_H */
