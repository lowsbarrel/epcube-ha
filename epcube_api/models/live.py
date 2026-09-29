from __future__ import annotations

from pydantic import Field

from ..const import WorkMode
from .base import ApiBool, ApiDateTime, ApiFloat, ApiInt, ApiStr, EpCubeModel, to_int_enum


class LiveSnapshot(EpCubeModel):
    # power is watts, energy is kWh, state of charge is a whole percent
    dev_id: ApiStr = None

    solar_power: ApiFloat = None
    grid_power: ApiFloat = None
    back_up_power: ApiFloat = Field(default=None, alias="backUpPower")
    non_back_up_power: ApiFloat = Field(default=None, alias="nonBackUpPower")
    ev_power: ApiFloat = None
    generator_power: ApiFloat = None

    grid_total_power: ApiFloat = None
    grid_half_power: ApiFloat = None
    solar_ac_power: ApiFloat = None
    solar_dc_power: ApiFloat = None

    solar_flow: ApiFloat = None
    back_up_flow_power: ApiFloat = Field(default=None, alias="backUpFlowPower")
    non_back_up_flow_power: ApiFloat = Field(default=None, alias="nonBackUpFlowPower")
    ev_flow_power: ApiFloat = None
    generator_flow_power: ApiFloat = None

    grid_power_a: ApiFloat = None
    grid_power_b: ApiFloat = None
    grid_power_c: ApiFloat = None
    back_up_power_a: ApiFloat = Field(default=None, alias="backUpPowerA")
    back_up_power_b: ApiFloat = Field(default=None, alias="backUpPowerB")
    back_up_power_c: ApiFloat = Field(default=None, alias="backUpPowerC")

    battery_soc: ApiInt = None
    battery_current_electricity: ApiFloat = None
    battery_pack_num: ApiInt = None

    grid_electricity: ApiFloat = None
    solar_electricity: ApiFloat = None
    solar_dc_electricity: ApiFloat = None
    solar_ac_electricity: ApiFloat = None
    back_up_electricity: ApiFloat = Field(default=None, alias="backUpElectricity")
    non_back_up_electricity: ApiFloat = Field(default=None, alias="nonBackUpElectricity")
    generator_electricity: ApiFloat = None
    ev_electricity: ApiFloat = None
    self_help_rate: ApiFloat = None

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
    exists_sg: ApiStr = None

    grid_light: ApiStr = None
    generator_light: ApiStr = None
    ev_light: ApiStr = None

    grid_power_failure_num: ApiInt = None
    off_grid_power_supply_time: ApiFloat = None
    lpp_time_duration: ApiInt = None
    lpc_time_duration: ApiInt = None

    # same instant twice: def_* is UTC, from_* is the site's local zone
    def_create_time: ApiDateTime = None
    def_timezone: ApiStr = Field(default=None, alias="defTimeZone")
    from_create_time: ApiDateTime = None
    from_timezone: ApiStr = Field(default=None, alias="fromTimeZone")
    from_type: ApiStr = None

    version: ApiStr = None
    payload_version: ApiInt = None
    grid_standard: ApiInt = None
    res_sn_number: ApiInt = Field(default=None, alias="ressNumber")
    is_new_device: ApiBool = None
    dev_type: ApiInt = None

    tou_type: ApiInt = None
    earning_yesterday: ApiFloat = None
    unit_default: ApiStr = None
    unit_smallest: ApiStr = None
    unit_multi: ApiStr = None

    winter_protect: ApiInt = None
    winter_mode: ApiInt = None
    has_evse: ApiBool = None
    evse_online: ApiBool = None
    system_special_work_mode: ApiInt = None
    heat_pump_settings_permission: ApiStr = None
    home_connect_auth: ApiInt = None

    off_on_grid_hint: ApiStr = Field(default=None, alias="off_ON_Grid_Hint")

    @property
    def mode(self) -> WorkMode | None:
        return to_int_enum(WorkMode, self.work_status)

    @property
    def load_power(self) -> float | None:
        if self.back_up_power is None and self.non_back_up_power is None:
            return None
        return (self.back_up_power or 0.0) + (self.non_back_up_power or 0.0)

    @property
    def load_electricity(self) -> float | None:
        if self.back_up_electricity is None and self.non_back_up_electricity is None:
            return None
        return (self.back_up_electricity or 0.0) + (self.non_back_up_electricity or 0.0)

    @property
    def battery_power(self) -> float | None:
        if self.solar_power is None or self.grid_power is None:
            return None
        return self.solar_power + self.grid_power - (self.load_power or 0.0)
