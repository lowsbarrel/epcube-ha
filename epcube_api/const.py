from __future__ import annotations

from datetime import date
from enum import IntEnum, StrEnum

# The mobile app's UA; the API does not enforce it, but every working client sends it.
USER_AGENT = "ReservoirMonitoring/2.1.0 (iPhone; iOS 18.3.2; Scale/3.00)"

DEFAULT_LANGUAGE = "en-US"

DEFAULT_TIMEOUT = 30.0
DEFAULT_CONNECT_TIMEOUT = 10.0

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF = 1.0
RATE_LIMIT_BACKOFF_MULTIPLIER = 2.0


class Region(StrEnum):
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
            return cls(value.strip().upper())
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

    def format_date(self, when: date) -> str:
        return when.strftime(self.date_format)

    @property
    def series_granularity(self) -> str:
        return {
            Scope.LIFETIME: "one year",
            Scope.DAY: "five minutes",
            Scope.MONTH: "one day",
            Scope.YEAR: "one month",
        }[self]


class SystemStatus(IntEnum):
    OFFLINE = 0
    STANDBY = 1
    CHARGING = 2
    DISCHARGING = 3
    ONLINE = 4


class DayType(IntEnum):
    WORKDAY = 1
    NON_WORKDAY = 2


# Weekday numbering used by activeWeek / activeWeekNonWorkDay: 1 = Monday.
DEFAULT_WORKDAYS = ("1", "2", "3", "4", "5")
DEFAULT_NON_WORKDAYS = ("6", "7")
