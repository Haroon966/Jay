package com.jay

/**
 * Protocol constants (must match protocol/SPEC.md, protocol/constants.json, and firmware).
 * Use standard SPP UUID so we can connect to ESP32 default SPP server.
 */
object Protocol {
    const val PROTOCOL_VERSION = 1
    const val SPP_SERVICE_UUID = "00001101-0000-1000-8000-00805F9B34FB"
    const val SAMPLE_RATE = 16000
    const val FRAME_SAMPLES = 320
    const val FRAME_MS = 20
    const val PACKET_HEADER_SIZE = 2
    const val MAX_PAYLOAD_LEN = 512
    const val DEVICE_NAME_PREFIX = "Helmet-"
    const val INTERCOM_RSSI_THRESHOLD_DBM = -70
    const val DISCOVERY_BACKOFF_MIN_MS = 1000
    const val DISCOVERY_BACKOFF_MAX_MS = 12000
}
