"""The live snapshot returned by `device/homeDeviceInfo`.

This is the app's home screen: instantaneous power flows, battery state, and the
day's running energy totals. It is also the only endpoint that reports `devId`,
which every other device endpoint requires.

Units, established by comparing against the app: **power is watts**, **energy is
kWh**, SoC is a whole percent. Note that `device/queryDataGraphV2` reports the
same power quantities in **kW** - the API is not internally consistent, so the
series model converts on the way in.

Field names here were checked against a live response rather than guessed. The
API's casing is not self-consistent - `backUpPower` but `backupLoadsMode`,
`defTimeZone` but `devId`, and `off_ON_Grid_Hint` in a class of its own - so any
field whose spelling does not fall out of plain camelCase carries an explicit
alias below.
"""

from __future__ import annotations

from pydantic import Field

from ..const import WorkMode
from .base import ApiBool, ApiDateTime, ApiFloat, ApiInt, ApiStr, EpCubeModel


class LiveSnapshot(EpCubeModel):
    """One instant of system state."""

    # --- identity ---
    dev_id: ApiStr = None
    """Numeric device id. Required by every other `device/*` endpoint."""

    # --- power flows, watts ---
    solar_power: ApiFloat = None
    grid_power: ApiFloat = None
    back_up_power: ApiFloat = Field(default=None, alias="backUpPower")
    """Load on the backup-protected circuits."""
    non_back_up_power: ApiFloat = Field(default=None, alias="nonBackUpPower")
    ev_power: ApiFloat = None
    generator_power: ApiFloat = None
    """On single-inverter systems this mirrors `solar_power` rather than being a
    separate generator input; treat it as an alias unless a generator is fitted."""

    grid_total_power: ApiFloat = None
    grid_half_power: ApiFloat = None
    solar_ac_power: ApiFloat = None
    solar_dc_power: ApiFloat = None

    # Flow variants, used by the app to animate the energy-flow diagram.
    solar_flow: ApiFloat = None
    back_up_flow_power: ApiFloat = Field(default=None, alias="backUpFlowPower")
    non_back_up_flow_power: ApiFloat = Field(default=None, alias="nonBackUpFlowPower")
    ev_flow_power: ApiFloat = None
    generator_flow_power: ApiFloat = None

    # Per-phase. All zero on single-phase systems; `deviceSystemType` on the
    # device record says which topology is fitted.
    grid_power_a: ApiFloat = None
    grid_power_b: ApiFloat = None
    grid_power_c: ApiFloat = None
    back_up_power_a: ApiFloat = Field(default=None, alias="backUpPowerA")
    back_up_power_b: ApiFloat = Field(default=None, alias="backUpPowerB")
    back_up_power_c: ApiFloat = Field(default=None, alias="backUpPowerC")

    # --- battery ---
    battery_soc: ApiInt = None
    """State of charge, whole percent."""
    battery_current_electricity: ApiFloat = None
    """Energy currently stored, kWh."""
    battery_pack_num: ApiInt = None

    # --- today's energy, kWh ---
    grid_electricity: ApiFloat = None
    solar_electricity: ApiFloat = None
    solar_dc_electricity: ApiFloat = None
    solar_ac_electricity: ApiFloat = None
    back_up_electricity: ApiFloat = Field(default=None, alias="backUpElectricity")
    non_back_up_electricity: ApiFloat = Field(default=None, alias="nonBackUpElectricity")
    generator_electricity: ApiFloat = None
    ev_electricity: ApiFloat = None
    self_help_rate: ApiFloat = None
    """Self-sufficiency, percent."""

    # --- status ---
    status: ApiStr = None
    system_status: ApiInt = None
    work_status: ApiStr = None
    is_online: ApiBool = None
    is_alert: ApiBool = None
    is_fault: ApiBool = None
    fault_warning_type: ApiStr = None
    signal_level: ApiInt = None
    networking: ApiInt = None
    back_up_type: ApiInt = Field(default=None, alias="backUpType")
    backup_loads_mode: ApiInt = None
    """Note the lowercase "up" - the API spells this one differently."""
    exists_sg: ApiStr = None

    # Indicator lamps the app renders on the flow diagram.
    grid_light: ApiStr = None
    generator_light: ApiStr = None
    ev_light: ApiStr = None

    grid_power_failure_num: ApiInt = None
    """Lifetime count of grid outages. `device/getDevPowerCutLog` has the events."""
    off_grid_power_supply_time: ApiFloat = None
    lpp_time_duration: ApiInt = None
    lpc_time_duration: ApiInt = None

    # --- timestamps: the same instant, twice ---
    def_create_time: ApiDateTime = None
    """Reading time in the zone named by `def_timezone` (UTC in practice)."""
    def_timezone: ApiStr = Field(default=None, alias="defTimeZone")
    from_create_time: ApiDateTime = None
    """The same reading in the site's local zone, named by `from_timezone`."""
    from_timezone: ApiStr = Field(default=None, alias="fromTimeZone")
    from_type: ApiStr = None

    # --- hardware / firmware ---
    version: ApiStr = None
    payload_version: ApiInt = None
    grid_standard: ApiInt = None
    res_sn_number: ApiInt = Field(default=None, alias="ressNumber")
    is_new_device: ApiBool = None
    dev_type: ApiInt = None

    # --- tariff metadata ---
    tou_type: ApiInt = None
    earning_yesterday: ApiFloat = None
    unit_default: ApiStr = None
    """Currency symbol, e.g. "€"."""
    unit_smallest: ApiStr = None
    unit_multi: ApiStr = None

    # --- comfort / auxiliary features ---
    winter_protect: ApiInt = None
    winter_mode: ApiInt = None
    has_evse: ApiBool = None
    evse_online: ApiBool = None
    system_special_work_mode: ApiInt = None
    heat_pump_settings_permission: ApiStr = None
    home_connect_auth: ApiInt = None

    off_on_grid_hint: ApiStr = Field(default=None, alias="off_ON_Grid_Hint")
    """A localized sentence describing the current mode, as shown in the app.
    Its key really is spelled like that."""

    @property
    def mode(self) -> WorkMode | None:
        """`work_status` as an enum, or None if the API sent something unknown."""
        try:
            return WorkMode(int(self.work_status))  # ty: ignore[invalid-argument-type]
        except (TypeError, ValueError):
            return None

    @property
    def load_power(self) -> float | None:
        """Total house load in watts: backup plus non-backup circuits."""
        if self.back_up_power is None and self.non_back_up_power is None:
            return None
        return (self.back_up_power or 0.0) + (self.non_back_up_power or 0.0)

    @property
    def battery_power(self) -> float | None:
        """Battery charge/discharge power in watts, derived. Positive = charging.

        This endpoint does not report battery power, so it has to be inferred
        from the other flows - and because those are sampled at slightly
        different instants, the result carries tens of watts of noise even with
        the battery at rest.

        Prefer `client.data.series(...)`: `device/queryDataGraphV2` reports
        `batteryPower` directly, at five-minute resolution.
        """
        if self.solar_power is None or self.grid_power is None:
            return None
        return self.solar_power + self.grid_power - (self.load_power or 0.0)
