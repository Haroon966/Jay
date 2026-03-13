/**
 * Jay – Main: NVS, SPP task (with RX callback), audio task
 */
#include "audio_task.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "spp_task.h"

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    if (spp_task_start(audio_task_spp_rx_cb, NULL) != 0) {
        ESP_LOGE("main", "spp_task_start failed");
        return;
    }
    if (audio_task_start() != 0) {
        ESP_LOGE("main", "audio_task_start failed");
        spp_task_stop();
        return;
    }
}
