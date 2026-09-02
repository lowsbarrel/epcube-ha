"""Constants, regions and enumerations for the EP Cube cloud API."""

from __future__ import annotations

from enum import IntEnum, StrEnum

# The mobile app's user agent. The API does not appear to enforce it, but every
# known working client sends it and it costs nothing to keep the traffic
# indistinguishable from the app's.
USER_AGENT = "ReservoirMonitoring/2.1.0 (iPhone; iOS 18.3.2; Scale/3.00)"

DEFAULT_LANGUAGE = "en-US"

# Timeouts, in seconds.
DEFAULT_TIMEOUT = 30.0
DEFAULT_CONNECT_TIMEOUT = 10.0

# Retry policy for transient failures (429, 5xx, timeouts, connection errors).
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF = 1.0
RATE_LIMIT_BACKOFF_MULTIPLIER = 2.0


class Region(StrEnum):
    """Regional clusters. An account exists on exactly one of them.

    A token minted on the wrong cluster is not rejected cleanly -- it comes back
    as "User token expired", which is why this is an explicit choice rather than
    something the client tries to discover.
    """

    EU = "EU"
    US = "US"
    JP = "JP"

    @property
    def base_url(self) -> str:
        return BASE_URLS[self]

    @classmethod
    def parse(cls, value: Region | str) -> Region:
        if isinstance(value, Region):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            raise ValueError(
                f"unknown region {value!r}; expected one of " + ", ".join(r.value for r in cls)
            ) from None


BASE_URLS: dict[Region, str] = {
    Region.EU: "https://monitoring-eu.epcube.com/api",
    Region.US: "https://epcube-monitoring.com/app-api",
    Region.JP: "https://monitoring-jp.epcube.com/api",
}


class WorkMode(IntEnum):
    """Operating mode, the `workStatus` field.

    Switching to TIME_OF_USE without also supplying a schedule leaves the device
    on an empty tariff calendar, so prefer `client.device.set_tou_schedule`.
    """

    SELF_CONSUMPTION = 1
    TIME_OF_USE = 2
    BACKUP = 3

    @property
    def label(self) -> str:
        return {
            WorkMode.SELF_CONSUMPTION: "Self-consumption",
            WorkMode.TIME_OF_USE: "Time of Use",
            WorkMode.BACKUP: "Backup",
        }[self]


class Scope(IntEnum):
    """`scopeType`, which selects both the aggregation window and the format
    `queryDateStr` must take.

    Passing a date in the wrong format is a server-side 500, not a validation
    error, so `Scope.format_date` exists to get it right.
    """

    LIFETIME = 0
    DAY = 1
    MONTH = 2
    YEAR = 3

    @property
    def date_format(self) -> str:
        return {
            Scope.LIFETIME: "%Y",
            Scope.DAY: "%Y-%m-%d",
            Scope.MONTH: "%Y-%m",
            Scope.YEAR: "%Y",
        }[self]

    def format_date(self, when) -> str:
        """Render a date/datetime the way this scope expects it."""
        return when.strftime(self.date_format)

    @property
    def series_granularity(self) -> str:
        """What one point of a `queryDataGraphV2` series covers at this scope."""
        return {
            Scope.LIFETIME: "one year",
            Scope.DAY: "five minutes",
            Scope.MONTH: "one day",
            Scope.YEAR: "one month",
        }[self]


class SystemStatus(IntEnum):
    """Observed `systemStatus` values. Undocumented; names are inferred."""

    OFFLINE = 0
    STANDBY = 1
    CHARGING = 2
    DISCHARGING = 3
    ONLINE = 4


class DayType(IntEnum):
    """Which TOU calendar applies today."""

    WORKDAY = 1
    NON_WORKDAY = 2


# Weekday numbering used by activeWeek / activeWeekNonWorkDay: 1 = Monday.
DEFAULT_WORKDAYS = ("1", "2", "3", "4", "5")
DEFAULT_NON_WORKDAYS = ("6", "7")
