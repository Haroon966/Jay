/**
 * Jay – SPP acceptor + initiator, discovery, packet framing
 */
#include "spp_task.h"
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_bt_device.h"
#include "esp_gap_bt_api.h"
#include "esp_log.h"
#include "esp_spp_api.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "spp";

#define SPP_RX_BUF_SIZE   (PACKET_HEADER_SIZE + MAX_PAYLOAD_LEN)
#define SPP_TX_QUEUE_LEN  8
#define DISCOVERY_INTERVAL_MS  8000

typedef struct {
    uint16_t len;
    uint8_t  data[MAX_PAYLOAD_LEN];
} tx_packet_t;

static spp_rx_cb_t s_rx_cb;
static void *s_rx_cb_arg;
static uint32_t s_spp_handle;
static volatile bool s_connected;
static esp_bd_addr_t s_peer_bda;  /* bda we are doing SPP discovery for */
static QueueHandle_t s_tx_queue;
static SemaphoreHandle_t s_mux;
static bool s_spp_init_done;

static void spp_cb(esp_spp_cb_event_t event, esp_spp_cb_param_t *param);
static void gap_cb(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t *param);
static void spp_parse_rx(const uint8_t *data, uint16_t len);
static void spp_task_loop(void *arg);

static void spp_parse_rx(const uint8_t *data, uint16_t len)
{
    static uint8_t parse_buf[SPP_RX_BUF_SIZE];
    static size_t parse_len;

    if (parse_len + len > SPP_RX_BUF_SIZE)
        parse_len = 0;
    memcpy(parse_buf + parse_len, data, len);
    parse_len += len;

    while (parse_len >= PACKET_HEADER_SIZE) {
        uint16_t plen = (uint16_t)parse_buf[0] | ((uint16_t)parse_buf[1] << 8);
        if (plen > MAX_PAYLOAD_LEN) {
            parse_len = 0;
            break;
        }
        if (parse_len < PACKET_HEADER_SIZE + plen)
            break;
        if (s_rx_cb)
            s_rx_cb(parse_buf + PACKET_HEADER_SIZE, plen, s_rx_cb_arg);
        size_t total = PACKET_HEADER_SIZE + plen;
        memmove(parse_buf, parse_buf + total, parse_len - total);
        parse_len -= total;
    }
}

static void spp_cb(esp_spp_cb_event_t event, esp_spp_cb_param_t *param)
{
    switch (event) {
    case ESP_SPP_INIT_EVT:
        s_spp_init_done = true;
        esp_spp_start_srv(ESP_SPP_SEC_NONE, ESP_SPP_ROLE_SLAVE, 0, SPP_SERVICE_NAME);
        break;
    case ESP_SPP_START_EVT:
        if (param->start.status == ESP_SPP_SUCCESS)
            ESP_LOGI(TAG, "SPP server started");
        break;
    case ESP_SPP_SRV_OPEN_EVT:
        if (param->srv_open.status == ESP_SPP_SUCCESS) {
            s_spp_handle = param->srv_open.handle;
            s_connected = true;
            ESP_LOGI(TAG, "SPP connected (server)");
        }
        break;
    case ESP_SPP_OPEN_EVT:
        if (param->open.status == ESP_SPP_SUCCESS) {
            s_spp_handle = param->open.handle;
            s_connected = true;
            ESP_LOGI(TAG, "SPP connected (client)");
        }
        break;
    case ESP_SPP_CLOSE_EVT:
        s_connected = false;
        s_spp_handle = 0;
        ESP_LOGI(TAG, "SPP closed");
        break;
    case ESP_SPP_DATA_IND_EVT:
        spp_parse_rx(param->data_ind.data, (uint16_t)param->data_ind.len);
        break;
    case ESP_SPP_DISCOVERY_COMP_EVT:
        if (param->disc_comp.status == ESP_SPP_SUCCESS && param->disc_comp.scn_num > 0) {
            uint8_t scn = param->disc_comp.scn[0];
            esp_spp_connect(ESP_SPP_SEC_NONE, ESP_SPP_ROLE_MASTER, scn, s_peer_bda);
        }
        break;
    default:
        break;
    }
}

static void gap_cb(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t *param)
{
    switch (event) {
    case ESP_BT_GAP_DISC_RES_EVT:
        if (s_connected)
            break;
        if (param->disc_res.num_prop && param->disc_res.bda) {
            const char *name = (const char *)param->disc_res.bdname;
            if (name && strncmp(name, INTERCOM_DEVICE_NAME_PREFIX, strlen(INTERCOM_DEVICE_NAME_PREFIX)) == 0) {
                memcpy(s_peer_bda, param->disc_res.bda, sizeof(esp_bd_addr_t));
                esp_spp_start_discovery(s_peer_bda);
            }
        }
        break;
    case ESP_BT_GAP_DISC_STATE_CHANGED_EVT:
        break;
    default:
        break;
    }
}

static void spp_task_loop(void *arg)
{
    while (1) {
        if (!s_connected) {
            esp_bt_gap_start_discovery(ESP_BT_INQ_MODE_GENERAL_INQUIRY, 10);
            vTaskDelay(pdMS_TO_TICKS(DISCOVERY_INTERVAL_MS));
            continue;
        }
        tx_packet_t pkt;
        if (xQueueReceive(s_tx_queue, &pkt, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (xSemaphoreTake(s_mux, pdMS_TO_TICKS(100)) == pdTRUE) {
                uint32_t h = s_spp_handle;
                xSemaphoreGive(s_mux);
                if (h && pkt.len <= MAX_PAYLOAD_LEN) {
                    uint8_t buf[PACKET_HEADER_SIZE + MAX_PAYLOAD_LEN];
                    buf[0] = (uint8_t)(pkt.len & 0xff);
                    buf[1] = (uint8_t)(pkt.len >> 8);
                    memcpy(buf + PACKET_HEADER_SIZE, pkt.data, pkt.len);
                    esp_spp_write(h, PACKET_HEADER_SIZE + pkt.len, buf);
                }
            }
        }
    }
}

int spp_task_start(spp_rx_cb_t rx_cb, void *arg)
{
    s_rx_cb = rx_cb;
    s_rx_cb_arg = arg;
    s_connected = false;
    s_spp_handle = 0;
    s_spp_init_done = false;

    s_tx_queue = xQueueCreate(SPP_TX_QUEUE_LEN, sizeof(tx_packet_t));
    s_mux = xSemaphoreCreateMutex();
    if (!s_tx_queue || !s_mux)
        return -1;

    esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    if (esp_bt_controller_init(&bt_cfg) != ESP_OK)
        return -1;
    if (esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT) != ESP_OK)
        return -1;
    if (esp_bluedroid_init() != ESP_OK)
        return -1;
    if (esp_bluedroid_enable() != ESP_OK)
        return -1;

    esp_bt_gap_register_callback(gap_cb);
    esp_spp_register_callback(spp_cb);
    esp_spp_cfg_t cfg = BT_SPP_DEFAULT_CONFIG();
    cfg.mode = ESP_SPP_MODE_CB;
    if (esp_spp_enhanced_init(&cfg) != ESP_OK)
        return -1;

    while (!s_spp_init_done)
        vTaskDelay(pdMS_TO_TICKS(50));

    esp_bt_dev_set_device_name(INTERCOM_DEVICE_NAME_PREFIX "ESP32");

    xTaskCreate(spp_task_loop, "spp", 4096, NULL, 5, NULL);
    return 0;
}

void spp_task_stop(void)
{
    if (s_spp_handle)
        esp_spp_disconnect(s_spp_handle);
    s_connected = false;
    esp_bluedroid_disable();
    esp_bluedroid_deinit();
    esp_bt_controller_disable();
    esp_bt_controller_deinit();
}

int spp_task_send(const uint8_t *payload, uint16_t payload_len)
{
    if (payload_len > MAX_PAYLOAD_LEN || !payload)
        return -1;
    tx_packet_t pkt;
    pkt.len = payload_len;
    memcpy(pkt.data, payload, payload_len);
    if (xQueueSend(s_tx_queue, &pkt, pdMS_TO_TICKS(200)) != pdTRUE)
        return -1;
    return 0;
}

int spp_task_is_connected(void)
{
    return s_connected ? 1 : 0;
}
