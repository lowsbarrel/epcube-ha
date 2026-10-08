from __future__ import annotations

import re
from typing import Any, Self, override

from pydantic import Field, field_validator

from ..const import DayType, WorkMode
from .base import ApiBool, ApiInt, ApiStr, ApiStrList, EpCubeModel, to_int_enum

_WINDOW_RE = re.compile(
    r"^(?P<start>(?:[01]?\d|2[0-4]):[0-5]\d)_"
    r"(?P<end>(?:[01]?\d|2[0-4]):[0-5]\d)"
    r"(?:_(?P<price>-?\d+(?:\.\d+)?))?$"
)


class TouWindow(EpCubeModel):
    start: str
    end: str
    price: float | None = None

    @classmethod
    def parse(cls, raw: str) -> Self | None:
        match = _WINDOW_RE.match(raw.strip())
        if not match:
            return None
        price = match.group("price")
        return cls(
            start=match.group("start"),
            end=match.group("end"),
            price=float(price) if price not in (None, "") else None,
        )

    @classmethod
    def parse_list(cls, raw: list[str] | None) -> list[Self]:
        return [w for w in (cls.parse(item) for item in raw or []) if w is not None]

    def to_api(self) -> str:
        if self.price is None:
            return f"{self.start}_{self.end}"
        price = f"{self.price:g}"
        return f"{self.start}_{self.end}_{price}"

    @override
    def __str__(self) -> str:
        return self.to_api()


class ModeConfig(EpCubeModel):
    dev_id: ApiStr = None
    work_status: ApiStr = None
    only_save: ApiStr = None
    weather_watch: ApiStr = None
    tou_type: ApiInt = None

    # alias is the API's misspelling; the correct spelling silently resets the value
    self_consumption_reserve_soc: ApiStr = Field(default=None, alias="selfConsumptioinReserveSoc")
    backup_power_reserve_soc: ApiStr = None
    ev_charger_reserve_soc: ApiInt = None
    charging_limit_soc: ApiInt = None

    # alias keeps the API's own "Xia" typo
    allow_charging_from_grid: ApiStr = Field(default=None, alias="allowChargingXiaGrid")

    peak_time_list: list[str] = Field(default_factory=list)
    mid_peak_time_list: list[str] = Field(default_factory=list)
    off_peak_time_list: list[str] = Field(default_factory=list)

    peak_time_list_non_work_day: list[str] = Field(default_factory=list)
    mid_peak_time_list_non_work_day: list[str] = Field(default_factory=list)
    off_peak_time_list_non_work_day: list[str] = Field(default_factory=list)

    day_light_peak_time_list: list[str] = Field(default_factory=list)
    day_light_mid_peak_time_list: list[str] = Field(default_factory=list)
    day_light_off_peak_time_list: list[str] = Field(default_factory=list)

    active_week: ApiStrList = Field(default_factory=list)
    active_week_non_work_day: ApiStrList = Field(default_factory=list)
    day_light_active_week: ApiStrList = Field(default_factory=list)
    day_light_active_week_non_work_day: ApiStrList = Field(default_factory=list)

    day_light_saving_time: ApiBool = None
    is_day_light_saving: ApiStr = Field(default=None, alias="isDayLightSaving")
    day_type: ApiInt = None
    exists_sg: ApiStr = None

    @field_validator(
        "peak_time_list",
        "mid_peak_time_list",
        "off_peak_time_list",
        "peak_time_list_non_work_day",
        "mid_peak_time_list_non_work_day",
        "off_peak_time_list_non_work_day",
        "day_light_peak_time_list",
        "day_light_mid_peak_time_list",
        "day_light_off_peak_time_list",
        mode="before",
    )
    @classmethod
    def _default_empty(cls, value: Any) -> Any:
        return value if value is not None else list[str]()

    @property
    def mode(self) -> WorkMode | None:
        return to_int_enum(WorkMode, self.work_status)

    @property
    def today_calendar(self) -> DayType | None:
        return to_int_enum(DayType, self.day_type)

    @property
    def grid_charging_allowed(self) -> bool:
        return str(self.allow_charging_from_grid) == "1"

    @property
    def peak_windows(self) -> list[TouWindow]:
        return TouWindow.parse_list(self.peak_time_list)

    @property
    def mid_peak_windows(self) -> list[TouWindow]:
        return TouWindow.parse_list(self.mid_peak_time_list)

    @property
    def off_peak_windows(self) -> list[TouWindow]:
        return TouWindow.parse_list(self.off_peak_time_list)

    @property
    def has_tou_schedule(self) -> bool:
        return any(
            (
                self.peak_time_list,
                self.mid_peak_time_list,
                self.off_peak_time_list,
                self.peak_time_list_non_work_day,
                self.mid_peak_time_list_non_work_day,
                self.off_peak_time_list_non_work_day,
            )
        )
