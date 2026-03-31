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

#define SPP_RX_BUF_SIZE   ((PACKET_HEADER_SIZE + MAX_PAYLOAD_LEN) * 4)
#define SPP_TX_QUEUE_LEN  8

typedef struct {
    uint16_t len;
    uint8_t  data[MAX_PAYLOAD_LEN];
} tx_packet_t;

typedef enum {
    SPP_STATE_IDLE = 0,
    SPP_STATE_SCANNING,
    SPP_STATE_CONNECTING,
    SPP_STATE_CONNECTED,
} spp_state_t;

static spp_rx_cb_t s_rx_cb;
static void *s_rx_cb_arg;
static uint32_t s_spp_handle;
static volatile bool s_connected;
static volatile spp_state_t s_state;
static esp_bd_addr_t s_peer_bda;  /* bda we are doing SPP discovery for */
static QueueHandle_t s_tx_queue;
static SemaphoreHandle_t s_mux;
static bool s_spp_init_done;
static bool s_bt_stack_ready;
static TaskHandle_t s_task_handle;
static volatile bool s_task_running;
static uint32_t s_discovery_backoff_ms = DISCOVERY_BACKOFF_MIN_MS;
static uint32_t s_rx_parser_overflows;
static uint32_t s_rx_parser_drops;
static uint32_t s_tx_queue_drops;
static uint32_t s_tx_write_errors;

static void spp_cb(esp_spp_cb_event_t event, esp_spp_cb_param_t *param);
static void gap_cb(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t *param);
static void spp_parse_rx(const uint8_t *data, uint16_t len);
static void spp_task_loop(void *arg);
static void spp_cleanup_runtime(void);
static void bump_discovery_backoff(void);
static bool disc_res_name_has_prefix(const esp_bt_gap_cb_param_t *param, const char *prefix);
static size_t ring_count(size_t head, size_t tail);
static uint8_t ring_peek_at(const uint8_t *buf, size_t tail, size_t offset);
static void ring_drop_bytes(size_t *tail, size_t count);
static void ring_read_bytes(const uint8_t *buf, size_t *tail, uint8_t *dst, size_t count);

static uint8_t s_parse_buf[SPP_RX_BUF_SIZE];
static size_t s_parse_head;
static size_t s_parse_tail;

static void bump_discovery_backoff(void)
{
    if (s_discovery_backoff_ms < DISCOVERY_BACKOFF_MAX_MS) {
        s_discovery_backoff_ms <<= 1;
        if (s_discovery_backoff_ms > DISCOVERY_BACKOFF_MAX_MS)
            s_discovery_backoff_ms = DISCOVERY_BACKOFF_MAX_MS;
    }
}

static bool disc_res_name_has_prefix(const esp_bt_gap_cb_param_t *param, const char *prefix)
{
    if (!param || !prefix)
        return false;

    size_t prefix_len = strlen(prefix);
    for (int i = 0; i < param->disc_res.num_prop; ++i) {
        const esp_bt_gap_dev_prop_t *prop = &param->disc_res.prop[i];
        if (!prop->val || prop->len <= 0)
            continue;

        if (prop->type == ESP_BT_GAP_DEV_PROP_BDNAME) {
            if ((size_t)prop->len >= prefix_len && memcmp(prop->val, prefix, prefix_len) == 0)
                return true;
            continue;
        }

        if (prop->type == ESP_BT_GAP_DEV_PROP_EIR) {
            uint8_t name_len = 0;
            uint8_t *name = esp_bt_gap_resolve_eir_data((uint8_t *)prop->val, ESP_BT_EIR_TYPE_CMPL_LOCAL_NAME, &name_len);
            if (!name) {
                name = esp_bt_gap_resolve_eir_data((uint8_t *)prop->val, ESP_BT_EIR_TYPE_SHORT_LOCAL_NAME, &name_len);
            }
            if (name && (size_t)name_len >= prefix_len && memcmp(name, prefix, prefix_len) == 0)
                return true;
        }
    }
    return false;
}

static size_t ring_count(size_t head, size_t tail)
{
    if (head >= tail)
        return head - tail;
    return SPP_RX_BUF_SIZE - tail + head;
}

static uint8_t ring_peek_at(const uint8_t *buf, size_t tail, size_t offset)
{
    return buf[(tail + offset) % SPP_RX_BUF_SIZE];
}

static void ring_drop_bytes(size_t *tail, size_t count)
{
    *tail = (*tail + count) % SPP_RX_BUF_SIZE;
}

static void ring_read_bytes(const uint8_t *buf, size_t *tail, uint8_t *dst, size_t count)
{
    for (size_t i = 0; i < count; ++i) {
        dst[i] = buf[*tail];
        *tail = (*tail + 1) % SPP_RX_BUF_SIZE;
    }
}

static void spp_parse_rx(const uint8_t *data, uint16_t len)
{
    if (!data || len == 0)
        return;

    for (uint16_t i = 0; i < len; ++i) {
        size_t next_head = (s_parse_head + 1) % SPP_RX_BUF_SIZE;
        if (next_head == s_parse_tail) {
            s_rx_parser_overflows++;
            ring_drop_bytes(&s_parse_tail, 1);
            if ((s_rx_parser_overflows % 100) == 1) {
                ESP_LOGW(TAG, "RX parser overflow drops=%lu", (unsigned long)s_rx_parser_overflows);
            }
        }
        s_parse_buf[s_parse_head] = data[i];
        s_parse_head = next_head;
    }

    while (ring_count(s_parse_head, s_parse_tail) >= PACKET_HEADER_SIZE) {
        uint16_t plen = (uint16_t)ring_peek_at(s_parse_buf, s_parse_tail, 0) |
                        ((uint16_t)ring_peek_at(s_parse_buf, s_parse_tail, 1) << 8);
        if (plen == 0 || plen > MAX_PAYLOAD_LEN) {
            ring_drop_bytes(&s_parse_tail, 1);
            s_rx_parser_drops++;
            if ((s_rx_parser_drops % 100) == 1) {
                ESP_LOGW(TAG, "RX parser malformed drops=%lu", (unsigned long)s_rx_parser_drops);
            }
            continue;
        }
        if (ring_count(s_parse_head, s_parse_tail) < (size_t)(PACKET_HEADER_SIZE + plen))
            break;
        ring_drop_bytes(&s_parse_tail, PACKET_HEADER_SIZE);
        if (s_rx_cb)
        {
            uint8_t payload[MAX_PAYLOAD_LEN];
            ring_read_bytes(s_parse_buf, &s_parse_tail, payload, plen);
            s_rx_cb(payload, plen, s_rx_cb_arg);
        } else {
            ring_drop_bytes(&s_parse_tail, plen);
        }
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
            s_state = SPP_STATE_CONNECTED;
            s_discovery_backoff_ms = DISCOVERY_BACKOFF_MIN_MS;
            ESP_LOGI(TAG, "SPP connected (server)");
        }
        break;
    case ESP_SPP_OPEN_EVT:
        if (param->open.status == ESP_SPP_SUCCESS) {
            s_spp_handle = param->open.handle;
            s_connected = true;
            s_state = SPP_STATE_CONNECTED;
            s_discovery_backoff_ms = DISCOVERY_BACKOFF_MIN_MS;
            ESP_LOGI(TAG, "SPP connected (client)");
        } else {
            s_connected = false;
            s_state = SPP_STATE_IDLE;
            bump_discovery_backoff();
            ESP_LOGW(TAG, "SPP open failed status=%d", param->open.status);
        }
        break;
    case ESP_SPP_CLOSE_EVT:
        s_connected = false;
        s_state = SPP_STATE_IDLE;
        bump_discovery_backoff();
        s_spp_handle = 0;
        ESP_LOGI(TAG, "SPP closed");
        break;
    case ESP_SPP_DATA_IND_EVT:
        spp_parse_rx(param->data_ind.data, (uint16_t)param->data_ind.len);
        break;
    case ESP_SPP_DISCOVERY_COMP_EVT:
        if (param->disc_comp.status == ESP_SPP_SUCCESS && param->disc_comp.scn_num > 0) {
            uint8_t scn = param->disc_comp.scn[0];
            s_state = SPP_STATE_CONNECTING;
            esp_err_t err = esp_spp_connect(ESP_SPP_SEC_NONE, ESP_SPP_ROLE_MASTER, scn, s_peer_bda);
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "SPP connect start failed err=0x%x", (unsigned int)err);
                s_state = SPP_STATE_IDLE;
                bump_discovery_backoff();
            }
        } else {
            s_state = SPP_STATE_IDLE;
            bump_discovery_backoff();
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
        if (s_connected || s_state != SPP_STATE_SCANNING)
            break;
        if (param->disc_res.num_prop && disc_res_name_has_prefix(param, INTERCOM_DEVICE_NAME_PREFIX)) {
            memcpy(s_peer_bda, param->disc_res.bda, sizeof(esp_bd_addr_t));
            s_state = SPP_STATE_CONNECTING;
            esp_bt_gap_cancel_discovery();
            esp_err_t err = esp_spp_start_discovery(s_peer_bda);
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "SPP service discovery start failed err=0x%x", (unsigned int)err);
                s_state = SPP_STATE_IDLE;
                bump_discovery_backoff();
            }
        }
        break;
    case ESP_BT_GAP_DISC_STATE_CHANGED_EVT:
        if (!s_connected && s_state == SPP_STATE_SCANNING &&
            param->disc_st_chg.state == ESP_BT_GAP_DISCOVERY_STOPPED) {
            s_state = SPP_STATE_IDLE;
        }
        break;
    default:
        break;
    }
}

static void spp_task_loop(void *arg)
{
    TickType_t last_discovery = xTaskGetTickCount();
    while (s_task_running) {
        if (!s_connected && s_state == SPP_STATE_IDLE) {
            TickType_t now = xTaskGetTickCount();
            if ((now - last_discovery) >= pdMS_TO_TICKS(s_discovery_backoff_ms)) {
                esp_err_t err = esp_bt_gap_start_discovery(ESP_BT_INQ_MODE_GENERAL_INQUIRY, 10, 0);
                if (err == ESP_OK) {
                    s_state = SPP_STATE_SCANNING;
                } else {
                    ESP_LOGW(TAG, "BT discovery start failed err=0x%x", (unsigned int)err);
                    s_state = SPP_STATE_IDLE;
                    bump_discovery_backoff();
                }
                last_discovery = now;
            }
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        tx_packet_t pkt;
        if (xQueueReceive(s_tx_queue, &pkt, pdMS_TO_TICKS(20)) == pdTRUE) {
            if (xSemaphoreTake(s_mux, pdMS_TO_TICKS(100)) == pdTRUE) {
                uint32_t h = s_spp_handle;
                xSemaphoreGive(s_mux);
                if (h && pkt.len <= MAX_PAYLOAD_LEN) {
                    uint8_t buf[PACKET_HEADER_SIZE + MAX_PAYLOAD_LEN];
                    buf[0] = (uint8_t)(pkt.len & 0xff);
                    buf[1] = (uint8_t)(pkt.len >> 8);
                    memcpy(buf + PACKET_HEADER_SIZE, pkt.data, pkt.len);
                    esp_err_t err = esp_spp_write(h, PACKET_HEADER_SIZE + pkt.len, buf);
                    if (err != ESP_OK) {
                        s_tx_write_errors++;
                        if ((s_tx_write_errors % 100) == 1) {
                            ESP_LOGW(TAG, "SPP write errors=%lu", (unsigned long)s_tx_write_errors);
                        }
                    }
                }
            }
        }
    }
    s_task_handle = NULL;
    vTaskDelete(NULL);
}

static void spp_cleanup_runtime(void)
{
    if (s_task_handle) {
        TaskHandle_t handle = s_task_handle;
        s_task_handle = NULL;
        vTaskDelete(handle);
    }
    if (s_spp_handle) {
        esp_spp_disconnect(s_spp_handle);
        s_spp_handle = 0;
    }
    if (s_bt_stack_ready) {
        esp_bluedroid_disable();
        esp_bluedroid_deinit();
        esp_bt_controller_disable();
        esp_bt_controller_deinit();
        s_bt_stack_ready = false;
    }
    if (s_tx_queue) {
        vQueueDelete(s_tx_queue);
        s_tx_queue = NULL;
    }
    if (s_mux) {
        vSemaphoreDelete(s_mux);
        s_mux = NULL;
    }
}

int spp_task_start(spp_rx_cb_t rx_cb, void *arg)
{
    if (s_task_running)
        return 0;

    s_rx_cb = rx_cb;
    s_rx_cb_arg = arg;
    s_task_running = true;
    s_connected = false;
    s_state = SPP_STATE_IDLE;
    s_spp_handle = 0;
    s_spp_init_done = false;
    s_bt_stack_ready = false;
    s_discovery_backoff_ms = DISCOVERY_BACKOFF_MIN_MS;
    s_parse_head = 0;
    s_parse_tail = 0;
    s_rx_parser_overflows = 0;
    s_rx_parser_drops = 0;
    s_tx_queue_drops = 0;
    s_tx_write_errors = 0;

    s_tx_queue = xQueueCreate(SPP_TX_QUEUE_LEN, sizeof(tx_packet_t));
    s_mux = xSemaphoreCreateMutex();
    if (!s_tx_queue || !s_mux) {
        s_task_running = false;
        spp_cleanup_runtime();
        return -1;
    }

    esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    if (esp_bt_controller_init(&bt_cfg) != ESP_OK) {
        s_task_running = false;
        spp_cleanup_runtime();
        return -1;
    }
    if (esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT) != ESP_OK) {
        s_task_running = false;
        spp_cleanup_runtime();
        return -1;
    }
    if (esp_bluedroid_init() != ESP_OK) {
        s_task_running = false;
        spp_cleanup_runtime();
        return -1;
    }
    if (esp_bluedroid_enable() != ESP_OK) {
        s_task_running = false;
        spp_cleanup_runtime();
        return -1;
    }
    s_bt_stack_ready = true;

    esp_bt_gap_register_callback(gap_cb);
    esp_spp_register_callback(spp_cb);
    esp_spp_cfg_t cfg = BT_SPP_DEFAULT_CONFIG();
    cfg.mode = ESP_SPP_MODE_CB;
    if (esp_spp_enhanced_init(&cfg) != ESP_OK) {
        s_task_running = false;
        spp_cleanup_runtime();
        return -1;
    }

    while (s_task_running && !s_spp_init_done)
        vTaskDelay(pdMS_TO_TICKS(50));

    esp_bt_dev_set_device_name(INTERCOM_DEVICE_NAME_PREFIX "ESP32");

    if (xTaskCreate(spp_task_loop, "spp", 4096, NULL, 5, &s_task_handle) != pdPASS) {
        s_task_running = false;
        spp_cleanup_runtime();
        return -1;
    }
    return 0;
}

void spp_task_stop(void)
{
    if (!s_task_running)
        return;
    s_task_running = false;
    s_connected = false;
    s_state = SPP_STATE_IDLE;
    spp_cleanup_runtime();
}

int spp_task_send(const uint8_t *payload, uint16_t payload_len)
{
    if (payload_len > MAX_PAYLOAD_LEN || !payload || !s_tx_queue || !s_connected)
        return -1;
    tx_packet_t pkt;
    pkt.len = payload_len;
    memcpy(pkt.data, payload, payload_len);
    if (xQueueSend(s_tx_queue, &pkt, 0) != pdTRUE) {
        s_tx_queue_drops++;
        if ((s_tx_queue_drops % 100) == 1) {
            ESP_LOGW(TAG, "SPP tx queue drops=%lu", (unsigned long)s_tx_queue_drops);
        }
        return -1;
    }
    return 0;
}

int spp_task_is_connected(void)
{
    return s_connected ? 1 : 0;
}
