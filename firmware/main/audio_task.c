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
#define I2S_DMA_BUF_LEN  1024

static i2s_chan_handle_t s_tx_handle;
static i2s_chan_handle_t s_rx_handle;
static QueueHandle_t s_playback_queue;
static TaskHandle_t s_task_handle;
static volatile bool s_running;

static void audio_task_loop(void *arg);

int audio_task_start(void)
{
    if (codec_init() != 0)
        return -1;

    s_playback_queue = xQueueCreate(PLAYBACK_QUEUE_LEN, sizeof(int16_t) * AUDIO_FRAME_SAMPLES);
    if (!s_playback_queue) {
        codec_deinit();
        return -1;
    }

    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM, I2S_ROLE_MASTER);
    i2s_chan_config_t rx_cfg = chan_cfg;
    i2s_chan_config_t tx_cfg = chan_cfg;
    esp_err_t err = i2s_new_channel(&tx_cfg, &s_tx_handle, &s_rx_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_new_channel %s", esp_err_to_name(err));
        vQueueDelete(s_playback_queue);
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
        codec_deinit();
        return -1;
    }

    i2s_channel_enable(s_tx_handle);
    i2s_channel_enable(s_rx_handle);

    s_running = true;
    xTaskCreate(audio_task_loop, "audio", 4096, NULL, 6, &s_task_handle);
    return 0;
}

void audio_task_stop(void)
{
    s_running = false;
    if (s_task_handle)
        vTaskDelay(pdMS_TO_TICKS(150));
    i2s_channel_disable(s_tx_handle);
    i2s_channel_disable(s_rx_handle);
    i2s_del_channel(s_tx_handle);
    i2s_del_channel(s_rx_handle);
    vQueueDelete(s_playback_queue);
    codec_deinit();
}

void audio_task_spp_rx_cb(const uint8_t *payload, uint16_t payload_len, void *arg)
{
    if (payload_len == 0 || payload == NULL)
        return;
    int16_t pcm[AUDIO_FRAME_SAMPLES];
    int n = codec_decode(payload, payload_len, pcm);
    if (n == AUDIO_FRAME_SAMPLES)
        xQueueSend(s_playback_queue, pcm, 0);
}

static void audio_task_loop(void *arg)
{
    int16_t mic_buf[AUDIO_FRAME_SAMPLES];
    uint8_t enc_buf[CODEC_MAX_FRAME_BYTES];
    size_t bytes_read;

    while (s_running) {
        esp_err_t err = i2s_channel_read(s_rx_handle, mic_buf, sizeof(mic_buf), &bytes_read, portMAX_DELAY);
        if (err != ESP_OK || bytes_read != sizeof(mic_buf))
            continue;
        if (spp_task_is_connected()) {
            int enc_len = codec_encode(mic_buf, enc_buf, sizeof(enc_buf));
            if (enc_len > 0)
                spp_task_send(enc_buf, (uint16_t)enc_len);
        }

        int16_t play_buf[AUDIO_FRAME_SAMPLES];
        if (xQueueReceive(s_playback_queue, play_buf, pdMS_TO_TICKS(5)) == pdTRUE) {
            size_t written;
            i2s_channel_write(s_tx_handle, play_buf, sizeof(play_buf), &written, portMAX_DELAY);
        }
    }
    vTaskDelete(NULL);
}
