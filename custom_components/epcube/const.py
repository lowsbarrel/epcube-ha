"""Constants for the EP Cube integration.

Protocol constants (base URLs, enums, the user agent) are not here - they live in
`epcube_api.const` and are imported. This module holds only what Home Assistant
itself needs: the domain, the config keys, and the defaults behind them.
"""

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

# Config entry data
CONF_REGION = "region"
CONF_TOKEN = "token"
CONF_SN = "sn"
CONF_DEVICE_ID = "device_id"

# Options
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_SERIES = "enable_series"
CONF_ENABLE_STATISTICS = "enable_statistics"

# The live endpoint is quick; 30s keeps entities responsive without hammering a
# cloud API that has no published rate limit.
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

# The five-minute time series is the only source of a *measured* battery power
# reading, so it is on by default - see EpCubeCoordinator for the cost.
DEFAULT_ENABLE_SERIES = True

# Monthly/yearly/lifetime totals change slowly and cost four extra requests per
# refresh, so they are opt-in.
DEFAULT_ENABLE_STATISTICS = False
