#!/usr/bin/env python3
"""Validate key protocol constants stay in sync across platforms."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol.constants_loader import load_constants

CONSTANTS = load_constants()


def _extract_kotlin_const(path: Path, name: str) -> str:
    data = path.read_text(encoding="utf-8")
    match = re.search(rf"const val {name}\s*=\s*(.+)", data)
    if not match:
        raise AssertionError(f"{name} not found in {path}")
    return match.group(1).strip().strip('"')


def _extract_c_define(path: Path, name: str) -> str:
    data = path.read_text(encoding="utf-8")
    match = re.search(rf"#define\s+{name}\s+(.+)", data)
    if not match:
        raise AssertionError(f"{name} not found in {path}")
    value = match.group(1).split("/*", 1)[0].strip().strip('"')
    return value


def test_android_constants_match_protocol_json():
    path = ROOT / "android/app/src/main/java/com/jay/Protocol.kt"
    assert _extract_kotlin_const(path, "PROTOCOL_VERSION") == str(CONSTANTS["protocol_version"])
    assert _extract_kotlin_const(path, "SPP_SERVICE_UUID") == CONSTANTS["spp_service_uuid"]
    assert _extract_kotlin_const(path, "SAMPLE_RATE") == str(CONSTANTS["audio_sample_rate"])
    assert _extract_kotlin_const(path, "FRAME_MS") == str(CONSTANTS["audio_frame_ms"])
    assert _extract_kotlin_const(path, "FRAME_SAMPLES") == str(CONSTANTS["audio_frame_samples"])
    assert _extract_kotlin_const(path, "PACKET_HEADER_SIZE") == str(CONSTANTS["packet_header_size"])
    assert _extract_kotlin_const(path, "MAX_PAYLOAD_LEN") == str(CONSTANTS["max_payload_len"])
    assert _extract_kotlin_const(path, "DEVICE_NAME_PREFIX") == CONSTANTS["device_name_prefix"]
    assert _extract_kotlin_const(path, "INTERCOM_RSSI_THRESHOLD_DBM") == str(CONSTANTS["intercom_rssi_threshold_dbm"])
    assert _extract_kotlin_const(path, "DISCOVERY_BACKOFF_MIN_MS") == str(CONSTANTS["discovery_backoff_min_ms"])
    assert _extract_kotlin_const(path, "DISCOVERY_BACKOFF_MAX_MS") == str(CONSTANTS["discovery_backoff_max_ms"])


def test_firmware_constants_match_protocol_json():
    path = ROOT / "firmware/main/app_config.h"
    assert _extract_c_define(path, "INTERCOM_PROTOCOL_VERSION") == str(CONSTANTS["protocol_version"])
    assert _extract_c_define(path, "INTERCOM_SPP_SERVICE_UUID_STR") == CONSTANTS["spp_service_uuid"]
    assert _extract_c_define(path, "INTERCOM_DEVICE_NAME_PREFIX") == CONSTANTS["device_name_prefix"]
    assert _extract_c_define(path, "AUDIO_SAMPLE_RATE") == str(CONSTANTS["audio_sample_rate"])
    assert _extract_c_define(path, "AUDIO_FRAME_MS") == str(CONSTANTS["audio_frame_ms"])
    assert _extract_c_define(path, "AUDIO_FRAME_SAMPLES") == str(CONSTANTS["audio_frame_samples"])
    assert _extract_c_define(path, "CODEC_BITRATE") == str(CONSTANTS["codec_bitrate"])
    assert _extract_c_define(path, "PACKET_HEADER_SIZE") == str(CONSTANTS["packet_header_size"])
    assert _extract_c_define(path, "MAX_PAYLOAD_LEN") == str(CONSTANTS["max_payload_len"])
    assert _extract_c_define(path, "INTERCOM_RSSI_THRESHOLD_DBM").strip("()") == str(CONSTANTS["intercom_rssi_threshold_dbm"])
    assert _extract_c_define(path, "DISCOVERY_BACKOFF_MIN_MS") == str(CONSTANTS["discovery_backoff_min_ms"])
    assert _extract_c_define(path, "DISCOVERY_BACKOFF_MAX_MS") == str(CONSTANTS["discovery_backoff_max_ms"])


def test_protocol_constants_header_matches_protocol_json():
    path = ROOT / "protocol/constants.h"
    assert _extract_c_define(path, "INTERCOM_PROTOCOL_VERSION") == str(CONSTANTS["protocol_version"])
    assert _extract_c_define(path, "INTERCOM_SPP_SERVICE_UUID_STR") == CONSTANTS["spp_service_uuid"]
    assert _extract_c_define(path, "INTERCOM_DEVICE_NAME_PREFIX") == CONSTANTS["device_name_prefix"]
    assert _extract_c_define(path, "AUDIO_SAMPLE_RATE") == str(CONSTANTS["audio_sample_rate"])
    assert _extract_c_define(path, "AUDIO_FRAME_MS") == str(CONSTANTS["audio_frame_ms"])
    assert _extract_c_define(path, "PACKET_HEADER_SIZE") == str(CONSTANTS["packet_header_size"])
    assert _extract_c_define(path, "MAX_PAYLOAD_LEN") == str(CONSTANTS["max_payload_len"])
    assert _extract_c_define(path, "INTERCOM_RSSI_THRESHOLD_DBM").strip("()") == str(CONSTANTS["intercom_rssi_threshold_dbm"])
    assert _extract_c_define(path, "DISCOVERY_BACKOFF_MIN_MS") == str(CONSTANTS["discovery_backoff_min_ms"])
    assert _extract_c_define(path, "DISCOVERY_BACKOFF_MAX_MS") == str(CONSTANTS["discovery_backoff_max_ms"])
    assert int(_extract_c_define(path, "INTERCOM_CTRL_MUTE"), 16) == CONSTANTS["control_bytes"]["mute"]
    assert int(_extract_c_define(path, "INTERCOM_CTRL_UNMUTE"), 16) == CONSTANTS["control_bytes"]["unmute"]
    assert int(_extract_c_define(path, "INTERCOM_CTRL_DISCONNECT"), 16) == CONSTANTS["control_bytes"]["disconnect"]


def run_all():
    test_android_constants_match_protocol_json()
    test_firmware_constants_match_protocol_json()
    test_protocol_constants_header_matches_protocol_json()
    print("test_constants_sync OK")


if __name__ == "__main__":
    run_all()

