from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "epcube"
MANUFACTURER = "Canadian Solar"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONF_REGION = "region"
CONF_TOKEN = "token"
CONF_SN = "sn"
CONF_DEVICE_ID = "device_id"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_STATISTICS_INTERVAL = "statistics_interval"
CONF_ENABLE_SERIES = "enable_series"
CONF_ENABLE_STATISTICS = "enable_statistics"

DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

DEFAULT_STATISTICS_INTERVAL = 1800
MIN_STATISTICS_INTERVAL = 300
MAX_STATISTICS_INTERVAL = 86400

# The series is the only source of a measured battery power reading, so it is on by default.
DEFAULT_ENABLE_SERIES = True

DEFAULT_ENABLE_STATISTICS = False
