/**
 * Jay – I2S full-duplex, encode mic -> SPP, SPP -> decode -> speaker
 */
#include "audio_task.h"
#include "codec.h"
#include "driver/i2s_std.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "spp_task.h"
#include <string.h>

static const char *TAG = "audio";

#define I2S_NUM          I2S_NUM_0
#define PLAYBACK_QUEUE_LEN  4
#define DECODE_QUEUE_LEN    8
#define I2S_DMA_BUF_LEN  1024

static i2s_chan_handle_t s_tx_handle;
static i2s_chan_handle_t s_rx_handle;
static QueueHandle_t s_playback_queue;
static QueueHandle_t s_decode_queue;
static TaskHandle_t s_capture_task_handle;
static TaskHandle_t s_playback_task_handle;
static volatile bool s_running;
static uint32_t s_decode_errors;
static uint32_t s_encode_errors;
static uint32_t s_i2s_read_errors;
static uint32_t s_spp_send_drops;
static uint32_t s_decode_queue_drops;
static uint32_t s_i2s_write_errors;

typedef struct {
    uint16_t len;
    uint8_t payload[MAX_PAYLOAD_LEN];
} decode_packet_t;

static void audio_capture_task(void *arg);
static void audio_playback_task(void *arg);

int audio_task_start(void)
{
    if (codec_init() != 0)
        return -1;

    s_playback_queue = xQueueCreate(PLAYBACK_QUEUE_LEN, sizeof(int16_t) * AUDIO_FRAME_SAMPLES);
    s_decode_queue = xQueueCreate(DECODE_QUEUE_LEN, sizeof(decode_packet_t));
    if (!s_playback_queue || !s_decode_queue) {
        if (s_playback_queue)
            vQueueDelete(s_playback_queue);
        if (s_decode_queue)
            vQueueDelete(s_decode_queue);
        codec_deinit();
        return -1;
    }

    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM, I2S_ROLE_MASTER);
    i2s_chan_config_t tx_cfg = chan_cfg;
    esp_err_t err = i2s_new_channel(&tx_cfg, &s_tx_handle, &s_rx_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_new_channel %s", esp_err_to_name(err));
        vQueueDelete(s_playback_queue);
        vQueueDelete(s_decode_queue);
        codec_deinit();
        return -1;
    }

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = I2S_BCK_GPIO,
            .ws = I2S_WS_GPIO,
            .dout = I2S_DO_GPIO,
            .din = I2S_DI_GPIO,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv = false,
            },
        },
    };

    err = i2s_channel_init_std_mode(s_tx_handle, &std_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_channel_init_std_mode tx %s", esp_err_to_name(err));
        i2s_del_channel(s_tx_handle);
        i2s_del_channel(s_rx_handle);
        vQueueDelete(s_playback_queue);
        vQueueDelete(s_decode_queue);
        codec_deinit();
        return -1;
    }
    err = i2s_channel_init_std_mode(s_rx_handle, &std_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_channel_init_std_mode rx %s", esp_err_to_name(err));
        i2s_channel_disable(s_tx_handle);
        i2s_del_channel(s_tx_handle);
        i2s_del_channel(s_rx_handle);
        vQueueDelete(s_playback_queue);
        vQueueDelete(s_decode_queue);
        codec_deinit();
        return -1;
    }

    i2s_channel_enable(s_tx_handle);
    i2s_channel_enable(s_rx_handle);

    s_running = true;
    xTaskCreate(audio_capture_task, "audio_cap", 4096, NULL, 7, &s_capture_task_handle);
    xTaskCreate(audio_playback_task, "audio_play", 4096, NULL, 6, &s_playback_task_handle);
    return 0;
}

void audio_task_stop(void)
{
    s_running = false;
    if (s_capture_task_handle || s_playback_task_handle)
        vTaskDelay(pdMS_TO_TICKS(150));
    i2s_channel_disable(s_tx_handle);
    i2s_channel_disable(s_rx_handle);
    i2s_del_channel(s_tx_handle);
    i2s_del_channel(s_rx_handle);
    vQueueDelete(s_playback_queue);
    vQueueDelete(s_decode_queue);
    s_playback_queue = NULL;
    s_decode_queue = NULL;
    codec_deinit();
}

void audio_task_spp_rx_cb(const uint8_t *payload, uint16_t payload_len, void *arg)
{
    (void)arg;
    if (!s_running || !s_decode_queue || payload_len == 0 || payload == NULL || payload_len > MAX_PAYLOAD_LEN)
        return;

    decode_packet_t pkt = { .len = payload_len };
    memcpy(pkt.payload, payload, payload_len);
    if (xQueueSend(s_decode_queue, &pkt, 0) != pdTRUE) {
        s_decode_queue_drops++;
        if ((s_decode_queue_drops % 100) == 1) {
            ESP_LOGW(TAG, "decode queue drops=%lu", (unsigned long)s_decode_queue_drops);
        }
    }
}

static void audio_capture_task(void *arg)
{
    int16_t mic_buf[AUDIO_FRAME_SAMPLES];
    uint8_t enc_buf[CODEC_MAX_FRAME_BYTES];
    size_t bytes_read;

    while (s_running) {
        esp_err_t err = i2s_channel_read(s_rx_handle, mic_buf, sizeof(mic_buf), &bytes_read, portMAX_DELAY);
        if (err != ESP_OK || bytes_read != sizeof(mic_buf)) {
            s_i2s_read_errors++;
            if ((s_i2s_read_errors % 100) == 1)
                ESP_LOGW(TAG, "i2s read errors=%lu", (unsigned long)s_i2s_read_errors);
            continue;
        }
        if (spp_task_is_connected()) {
            int enc_len = codec_encode(mic_buf, enc_buf, sizeof(enc_buf));
            if (enc_len > 0) {
                if (spp_task_send(enc_buf, (uint16_t)enc_len) != 0) {
                    s_spp_send_drops++;
                    if ((s_spp_send_drops % 100) == 1) {
                        ESP_LOGW(TAG, "spp send drops=%lu", (unsigned long)s_spp_send_drops);
                    }
                }
            } else {
                s_encode_errors++;
                if ((s_encode_errors % 100) == 1)
                    ESP_LOGW(TAG, "codec encode errors=%lu", (unsigned long)s_encode_errors);
            }
        }
    }
    vTaskDelete(NULL);
}

static void audio_playback_task(void *arg)
{
    int16_t play_buf[AUDIO_FRAME_SAMPLES];
    decode_packet_t pkt;

    while (s_running) {
        if (!s_decode_queue || xQueueReceive(s_decode_queue, &pkt, pdMS_TO_TICKS(20)) != pdTRUE)
            continue;
        int n = codec_decode(pkt.payload, pkt.len, play_buf);
        if (n != AUDIO_FRAME_SAMPLES) {
            s_decode_errors++;
            if ((s_decode_errors % 100) == 1)
                ESP_LOGW(TAG, "codec decode errors=%lu", (unsigned long)s_decode_errors);
            continue;
        }
        if (s_playback_queue) {
            if (xQueueSend(s_playback_queue, play_buf, 0) != pdTRUE) {
                int16_t discard[AUDIO_FRAME_SAMPLES];
                xQueueReceive(s_playback_queue, discard, 0);
                xQueueSend(s_playback_queue, play_buf, 0);
            }
        }
        int16_t out_buf[AUDIO_FRAME_SAMPLES];
        if (!s_playback_queue || xQueueReceive(s_playback_queue, out_buf, 0) != pdTRUE)
            continue;
        size_t written = 0;
        esp_err_t err = i2s_channel_write(s_tx_handle, out_buf, sizeof(out_buf), &written, pdMS_TO_TICKS(20));
        if (err != ESP_OK || written != sizeof(out_buf)) {
            s_i2s_write_errors++;
            if ((s_i2s_write_errors % 100) == 1)
                ESP_LOGW(TAG, "i2s write errors=%lu", (unsigned long)s_i2s_write_errors);
        }
    }
    vTaskDelete(NULL);
}
