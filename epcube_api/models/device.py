"""Device identity, hardware detail and the per-device telemetry endpoints."""

from __future__ import annotations

import json
from typing import Any, Self

from pydantic import Field, field_validator

from .base import ApiBool, ApiDateTime, ApiFloat, ApiInt, ApiStr, EpCubeModel


class DeviceSummary(EpCubeModel):
    """One entry from `device/deviceList` - the richest metadata the API offers.

    Most of this appears nowhere else: component serials, install lineage,
    licensed features, coordinates.
    """

    id: ApiStr = None
    """The numeric device id used by every other `device/*` endpoint."""
    sg_sn: ApiStr = None
    """Plant serial - what `homeDeviceInfo` takes as `sgSn`."""
    rtu_sn: ApiStr = None
    sn_items: ApiStr = None
    """Comma-separated serials of the individual modules (battery packs, inverter)."""
    name: ApiStr = None

    status: ApiStr = None
    system_status: ApiInt = None
    work_status: ApiStr = None
    child_device_status: ApiStr = None
    """Per-slot status bitmap, one character per module bay. Undocumented."""
    is_online: ApiBool = None
    is_fault: ApiBool = None
    networking: ApiInt = None

    # --- topology ---
    device_system_type: ApiStr = None
    """e.g. "1Phase" or "3Phase"."""
    system_capacity: ApiFloat = None
    """Total usable capacity, kWh (the API sends e.g. "15.0kWh")."""
    battery_type: ApiFloat = None
    """Capacity of a single pack, kWh."""
    battery_pack_num: ApiInt = None
    is_parallel: ApiBool = None
    hybrid_num: ApiInt = None

    # --- firmware ---
    version: ApiStr = None
    software_version: ApiStr = None
    aotu_update_firmware: ApiStr = None
    """Auto-update flag. The API's own misspelling of "auto"."""

    # --- licensed features ---
    dynamic_price_auth: ApiStr = None
    eebus_authority: ApiInt = None
    keba_authority: ApiInt = None
    has_evse: ApiBool = None

    # --- account lineage ---
    user_id: ApiStr = None
    user_email: ApiStr = None
    install_user_id: ApiStr = None
    eu_distributor_id_multi: ApiStr = None
    create_by: ApiStr = None

    # --- location ---
    lat: ApiFloat = None
    lon: ApiFloat = None
    city: ApiStr = None
    """Frequently holds the longitude rather than a city name - an upstream bug."""
    mail_code: ApiStr = None
    address_info: ApiStr = None
    address_ids: ApiStr = None
    time_zone: ApiStr = None

    # --- timestamps ---
    create_time: ApiDateTime = None
    update_time: ApiDateTime = None
    install_time: ApiDateTime = None
    bing_time: ApiDateTime = None
    """Bind time. The API's own misspelling of "bind"."""
    last_connect_time: ApiDateTime = None

    tou_type: ApiInt = None
    dev_type: ApiInt = None
    rtu_type: ApiInt = None
    install_user_id_multi: ApiStr = None
    last_connect: ApiStr = None
    last_connect2: ApiStr = None
    del_flag: ApiStr = None
    test_data: ApiStr = None
    remark: ApiStr = None
    exists_sg: ApiStr = None

    work_param: dict[str, Any] = Field(default_factory=dict)
    """Mode and reserve settings, transported as a JSON *string* by the API and
    parsed here. A stale mirror of `getSwitchMode`; prefer that endpoint."""

    @field_validator("work_param", mode="before")
    @classmethod
    def _parse_work_param(cls, value: Any) -> Any:
        if isinstance(value, str):
            if not value.strip():
                return {}
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return value or {}

    @property
    def module_serials(self) -> list[str]:
        """`sn_items` split into individual module serial numbers."""
        return [s for s in (self.sn_items or "").split(",") if s]

    @property
    def is_single_phase(self) -> bool | None:
        if not self.device_system_type:
            return None
        return self.device_system_type.strip().lower().startswith("1")


class DeviceDetail(EpCubeModel):
    """`device/userDeviceInfo` - model, warranty and owner address."""

    name: ApiStr = None
    sg_sn: ApiStr = None
    rtu_sn: ApiStr = None
    model_type: ApiStr = None
    battery_capacity: ApiFloat = None
    """kWh; the API sends e.g. "15kWh"."""
    activation_data: ApiDateTime = None
    """Activation date. "data" is the API's own spelling of "date"."""
    warranty_data: ApiDateTime = None
    country: ApiStr = None
    state: ApiStr = None
    address: ApiStr = None
    address_info: ApiStr = None
    address_ids: ApiStr = None
    zip_code: ApiStr = None

    # `model_` is pydantic's reserved prefix, so the field is named model_type and
    # would collide with BaseModel internals if it were bare `model`.
    model_config = EpCubeModel.model_config | {"protected_namespaces": ()}


class Warranty(EpCubeModel):
    """`device/getWarranty`."""

    sg_sn: ApiStr = None
    name: ApiStr = None
    activation_date: ApiDateTime = None
    usage_end_date: ApiDateTime = None

    @property
    def years(self) -> float | None:
        if self.activation_date is None or self.usage_end_date is None:
            return None
        return (self.usage_end_date - self.activation_date).days / 365.25


class NetworkInfo(EpCubeModel):
    """`device/netWorkInfo` - how the unit is reaching the cloud."""

    networking: ApiInt = None
    wifi_name: ApiStr = None
    wifi_status: ApiInt = None
    wifi_status_str: ApiStr = None
    """Localized status text, in the account's language."""
    signal_level: ApiInt = None


class PvString(EpCubeModel):
    """One MPPT input: voltage, current and power."""

    index: int
    voltage: float | None = None
    current: float | None = None
    power: float | None = None
    """kW, as sent."""

    @property
    def power_w(self) -> float | None:
        return None if self.power is None else self.power * 1000.0

    @property
    def is_active(self) -> bool:
        return bool(self.voltage) or bool(self.current)


class PvStrings(EpCubeModel):
    """`device/getSolarPvPower` - per-string solar telemetry.

    The only endpoint exposing individual MPPT inputs. Nothing else in the API
    distinguishes one string from another, which makes this the only way to spot
    a shaded, dirty or failing string from the cloud side.
    """

    strings: list[PvString] = Field(default_factory=list)

    @classmethod
    def from_api(cls, payload: Any) -> Self:
        """Parse the flat `pv1Voltage` / `pv1Current` / `pv1Power` shape.

        The endpoint returns a single-element list; the number of inputs is not
        declared, so it is discovered from the keys present.
        """
        record: dict[str, Any] = {}
        if isinstance(payload, list):
            record = payload[0] if payload and isinstance(payload[0], dict) else {}
        elif isinstance(payload, dict):
            record = payload

        def number(key: str) -> float | None:
            raw = record.get(key)
            if raw in (None, ""):
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

        indexes = sorted(
            {
                int(key[2])
                for key in record
                if key.startswith("pv") and len(key) > 3 and key[2].isdigit()
            }
        )
        return cls(
            strings=[
                PvString(
                    index=i,
                    voltage=number(f"pv{i}Voltage"),
                    current=number(f"pv{i}Current"),
                    power=number(f"pv{i}Power"),
                )
                for i in indexes
            ]
        )

    @property
    def active(self) -> list[PvString]:
        return [s for s in self.strings if s.is_active]

    @property
    def total_power_w(self) -> float:
        return sum(s.power_w or 0.0 for s in self.strings)


class OutageEvent(EpCubeModel):
    """One grid outage from `device/getDevPowerCutLog`.

    The live snapshot only carries a running count (`grid_power_failure_num`);
    this is the event log behind it.
    """

    id: ApiStr = None
    dev_id: ApiStr = None
    rtu_sn: ApiStr = None
    sg_sn: ApiStr = None
    status: ApiInt = None
    duration: ApiStr = None
    """Human-readable, e.g. "7m"."""
    start_time: ApiDateTime = None
    end_time: ApiDateTime = None

    @property
    def minutes(self) -> float | None:
        """Duration computed from the timestamps, rather than parsing the label."""
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() / 60.0

    @property
    def ongoing(self) -> bool:
        return self.end_time is None
