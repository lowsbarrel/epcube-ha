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
CONF_STATISTICS_INTERVAL = "statistics_interval"
CONF_ENABLE_SERIES = "enable_series"
CONF_ENABLE_STATISTICS = "enable_statistics"
CONF_IMPORT_HISTORY = "import_history"

# The live read is quick; the fast loop keeps the power/SoC entities responsive.
# 60s halves the request rate of the old 30s default while still reading as live.
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

# The heavy reads - device details, outage log, the totals and the five-minute
# series - run on their own slower loop rather than every fast cycle: the live
# tier (live, mode, PV) stays responsive while these, which barely move within
# half an hour, stop dominating the request rate. The coordinator carries their
# last values forward between runs so their sensors never blank out.
DEFAULT_STATISTICS_INTERVAL = 1800
MIN_STATISTICS_INTERVAL = 300
MAX_STATISTICS_INTERVAL = 86400

# The five-minute time series is the only source of a *measured* battery power
# reading, so it is on by default - see EpCubeCoordinator for the cost.
DEFAULT_ENABLE_SERIES = True

# Monthly/yearly/lifetime totals change slowly, so they are opt-in. When on they
# are read on the statistics loop, not every refresh.
DEFAULT_ENABLE_STATISTICS = False

# Backfill the device's own daily energy history into HA statistics (as external
# `epcube:*` series) so the Energy dashboard shows the days before install. On by
# default: it is read-only against the API and only writes its own statistic ids.
DEFAULT_IMPORT_HISTORY = True
