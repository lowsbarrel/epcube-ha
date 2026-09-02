"""Operating mode and time-of-use configuration (`device/getSwitchMode`).

This is the read side of `device/switchMode`, and the source of truth a write
has to echo back: the write endpoint resets any field the payload omits, so a
partial update silently wipes the tariff calendar and the reserve levels. See
`models.requests.SwitchModeRequest`, which is built to make that impossible.
"""

from __future__ import annotations

import re
from typing import Any, Self

from pydantic import Field, field_validator

from ..const import DayType, WorkMode
from .base import ApiBool, ApiFloat, ApiInt, ApiStr, ApiStrList, EpCubeModel

# "08:00_12:00_0.31" -> start, end, price. The price is optional in practice.
_WINDOW_RE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2})_(?P<end>\d{1,2}:\d{2})(?:_(?P<price>[-\d.]+))?$"
)


class TouWindow(EpCubeModel):
    """One tariff window.

    The API transports these as opaque strings (`"08:00_12:00_0.31"`); this model
    parses them and renders back to the exact same format, so a round trip
    through it is lossless.
    """

    start: str
    end: str
    price: float | None = None

    @classmethod
    def parse(cls, raw: str) -> Self | None:
        """Parse one API window string. Returns None if it is malformed."""
        match = _WINDOW_RE.match(str(raw).strip())
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
        """Render back to the API's `HH:MM_HH:MM_price` form."""
        if self.price is None:
            return f"{self.start}_{self.end}"
        # The API accepts a plain decimal; keep it short but exact.
        price = f"{self.price:g}"
        return f"{self.start}_{self.end}_{price}"

    def __str__(self) -> str:
        return self.to_api()


class ModeConfig(EpCubeModel):
    """Current mode, reserve levels and the full tariff calendar."""

    dev_id: ApiStr = None
    work_status: ApiStr = None
    only_save: ApiStr = None
    weather_watch: ApiStr = None
    tou_type: ApiInt = None

    # --- reserve levels, percent ---
    self_consumption_reserve_soc: ApiStr = Field(default=None, alias="selfConsumptioinReserveSoc")
    """Floor the battery is held above in self-consumption mode.

    The alias preserves an upstream misspelling ("Consumptioin"); sending the
    correctly-spelled key is silently ignored, which resets the value.
    """
    backup_power_reserve_soc: ApiStr = None
    ev_charger_reserve_soc: ApiInt = None
    charging_limit_soc: ApiInt = None

    allow_charging_from_grid: ApiStr = Field(default=None, alias="allowChargingXiaGrid")
    """Whether the battery may charge from the grid. "1" = yes."""

    # --- tariff calendar: workdays ---
    peak_time_list: list[str] = Field(default_factory=list)
    mid_peak_time_list: list[str] = Field(default_factory=list)
    off_peak_time_list: list[str] = Field(default_factory=list)

    # --- tariff calendar: non-workdays ---
    peak_time_list_non_work_day: list[str] = Field(default_factory=list)
    mid_peak_time_list_non_work_day: list[str] = Field(default_factory=list)
    off_peak_time_list_non_work_day: list[str] = Field(default_factory=list)

    # --- tariff calendar: daylight-saving variants ---
    day_light_peak_time_list: list[str] = Field(default_factory=list)
    day_light_mid_peak_time_list: list[str] = Field(default_factory=list)
    day_light_off_peak_time_list: list[str] = Field(default_factory=list)

    # --- which weekdays each calendar applies to; 1 = Monday ---
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
        return [] if value is None else value

    @property
    def mode(self) -> WorkMode | None:
        try:
            return WorkMode(int(self.work_status))  # ty: ignore[invalid-argument-type]
        except (TypeError, ValueError):
            return None

    @property
    def today_calendar(self) -> DayType | None:
        try:
            return DayType(int(self.day_type))  # ty: ignore[invalid-argument-type]
        except (TypeError, ValueError):
            return None

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
        """Whether any tariff window is configured at all.

        Switching to `WorkMode.TIME_OF_USE` with this False leaves the device on
        an empty calendar, which is not a useful state.
        """
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


class ReserveLevels(EpCubeModel):
    """Just the reserve percentages, for callers that only want those."""

    self_consumption: ApiFloat = None
    backup: ApiFloat = None
    ev_charger: ApiFloat = None
    charging_limit: ApiFloat = None

    @classmethod
    def from_config(cls, config: ModeConfig) -> Self:
        return cls(
            self_consumption=config.self_consumption_reserve_soc,
            backup=config.backup_power_reserve_soc,
            ev_charger=config.ev_charger_reserve_soc,
            charging_limit=config.charging_limit_soc,
        )
