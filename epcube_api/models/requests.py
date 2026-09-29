from __future__ import annotations

from typing import Any, Self, override

from pydantic import Field

from ..const import DEFAULT_NON_WORKDAYS, DEFAULT_WORKDAYS, WorkMode
from .base import EpCubeRequest, to_int_enum
from .mode import ModeConfig, TouWindow


def _windows_to_api(windows: list[TouWindow] | list[str] | None) -> list[str]:
    if not windows:
        return []
    return [w.to_api() if isinstance(w, TouWindow) else w for w in windows]


class SwitchModeRequest(EpCubeRequest):
    dev_id: str = Field(alias="devId")
    work_status: str = Field(alias="workStatus")

    weather_watch: str = Field(default="0", alias="weatherWatch")
    only_save: str = Field(default="0", alias="onlySave")
    tou_type: int = Field(default=0, alias="touType")

    peak_time_list: list[str] = Field(default_factory=list, alias="peakTimeList")
    mid_peak_time_list: list[str] = Field(default_factory=list, alias="midPeakTimeList")
    off_peak_time_list: list[str] = Field(default_factory=list, alias="offPeakTimeList")
    peak_time_list_non_work_day: list[str] = Field(
        default_factory=list, alias="peakTimeListNonWorkDay"
    )
    mid_peak_time_list_non_work_day: list[str] = Field(
        default_factory=list, alias="midPeakTimeListNonWorkDay"
    )
    off_peak_time_list_non_work_day: list[str] = Field(
        default_factory=list, alias="offPeakTimeListNonWorkDay"
    )
    day_light_peak_time_list: list[str] = Field(default_factory=list, alias="dayLightPeakTimeList")
    day_light_mid_peak_time_list: list[str] = Field(
        default_factory=list, alias="dayLightMidPeakTimeList"
    )
    day_light_off_peak_time_list: list[str] = Field(
        default_factory=list, alias="dayLightOffPeakTimeList"
    )

    # activeWeek values must be strings; the API rejects integers
    active_week: list[str] = Field(
        default_factory=lambda: list(DEFAULT_WORKDAYS), alias="activeWeek"
    )
    active_week_non_work_day: list[str] = Field(
        default_factory=lambda: list(DEFAULT_NON_WORKDAYS), alias="activeWeekNonWorkDay"
    )
    day_light_active_week: list[str] = Field(
        default_factory=lambda: list(DEFAULT_WORKDAYS), alias="dayLightActiveWeek"
    )
    day_light_active_week_non_work_day: list[str] = Field(
        default_factory=lambda: list(DEFAULT_NON_WORKDAYS),
        alias="dayLightActiveWeekNonWorkDay",
    )

    day_light_saving_time: bool = Field(default=False, alias="dayLightSavingTime")

    # alias is the API's misspelling; the correct spelling silently resets the value
    self_consumption_reserve_soc: str = Field(default="5", alias="selfConsumptioinReserveSoc")
    backup_power_reserve_soc: str = Field(default="50", alias="backupPowerReserveSoc")
    allow_charging_from_grid: str = Field(default="1", alias="allowChargingXiaGrid")

    ev_charger_reserve_soc: int | None = Field(default=None, alias="evChargerReserveSoc")

    @classmethod
    def from_config(
        cls,
        config: ModeConfig,
        *,
        dev_id: str | None = None,
        work_status: WorkMode | int | str | None = None,
        only_save: bool = False,
    ) -> Self:
        resolved_id = dev_id or config.dev_id
        if not resolved_id:
            raise ValueError(
                "no device id: pass dev_id, or read the config from a device that reports one"
            )

        mode = work_status if work_status is not None else config.work_status
        if isinstance(mode, WorkMode):
            mode = mode.value

        return cls(
            devId=resolved_id,
            workStatus=str(mode if mode is not None else WorkMode.SELF_CONSUMPTION.value),
            onlySave="1" if only_save else "0",
            touType=config.tou_type if config.tou_type is not None else 0,
            peakTimeList=list(config.peak_time_list),
            midPeakTimeList=list(config.mid_peak_time_list),
            offPeakTimeList=list(config.off_peak_time_list),
            peakTimeListNonWorkDay=list(config.peak_time_list_non_work_day),
            midPeakTimeListNonWorkDay=list(config.mid_peak_time_list_non_work_day),
            offPeakTimeListNonWorkDay=list(config.off_peak_time_list_non_work_day),
            dayLightPeakTimeList=list(config.day_light_peak_time_list),
            dayLightMidPeakTimeList=list(config.day_light_mid_peak_time_list),
            dayLightOffPeakTimeList=list(config.day_light_off_peak_time_list),
            activeWeek=list(config.active_week) or list(DEFAULT_WORKDAYS),
            activeWeekNonWorkDay=(
                list(config.active_week_non_work_day) or list(DEFAULT_NON_WORKDAYS)
            ),
            dayLightActiveWeek=list(config.day_light_active_week) or list(DEFAULT_WORKDAYS),
            dayLightActiveWeekNonWorkDay=(
                list(config.day_light_active_week_non_work_day) or list(DEFAULT_NON_WORKDAYS)
            ),
            dayLightSavingTime=bool(config.day_light_saving_time),
            selfConsumptioinReserveSoc=str(
                config.self_consumption_reserve_soc
                if config.self_consumption_reserve_soc is not None
                else 5
            ),
            backupPowerReserveSoc=str(
                config.backup_power_reserve_soc
                if config.backup_power_reserve_soc is not None
                else 50
            ),
            allowChargingXiaGrid=str(
                config.allow_charging_from_grid
                if config.allow_charging_from_grid is not None
                else 1
            ),
        )

    def with_changes(self, **changes: Any) -> Self:
        return self.model_copy(update=self._normalise(changes))

    def _normalise(self, changes: dict[str, Any]) -> dict[str, Any]:
        by_alias = {
            field.alias: name for name, field in type(self).model_fields.items() if field.alias
        }
        out: dict[str, Any] = {}
        for key, value in changes.items():
            name = key if key in type(self).model_fields else by_alias.get(key)
            if name is None:
                raise ValueError(f"unknown switchMode field: {key!r}")
            out[name] = value
        return out

    def set_tou_schedule(
        self,
        *,
        peak: list[TouWindow] | list[str] | None = None,
        mid_peak: list[TouWindow] | list[str] | None = None,
        off_peak: list[TouWindow] | list[str] | None = None,
        peak_non_workday: list[TouWindow] | list[str] | None = None,
        mid_peak_non_workday: list[TouWindow] | list[str] | None = None,
        off_peak_non_workday: list[TouWindow] | list[str] | None = None,
    ) -> Self:
        changes: dict[str, Any] = {}
        for name, value in (
            ("peak_time_list", peak),
            ("mid_peak_time_list", mid_peak),
            ("off_peak_time_list", off_peak),
            ("peak_time_list_non_work_day", peak_non_workday),
            ("mid_peak_time_list_non_work_day", mid_peak_non_workday),
            ("off_peak_time_list_non_work_day", off_peak_non_workday),
        ):
            if value is not None:
                changes[name] = _windows_to_api(value)
        return self.model_copy(update=changes)

    @property
    def mode(self) -> WorkMode | None:
        return to_int_enum(WorkMode, self.work_status)

    @override
    def api_dump(self) -> dict[str, Any]:
        payload = super().api_dump()
        if payload.get("evChargerReserveSoc") is None:
            payload.pop("evChargerReserveSoc", None)
        return payload
