from __future__ import annotations

from epcube_api import ModeConfig, SwitchModeRequest, TouWindow, WorkMode
from epcube_api.const import DayType
from epcube_api.models.mode import ReserveLevels


def test_tou_window_parsing_round_trips():
    window = TouWindow.parse("08:00_12:00_0.31")
    assert window is not None
    assert (window.start, window.end, window.price) == ("08:00", "12:00", 0.31)
    assert window.to_api() == "08:00_12:00_0.31"
    assert str(window) == "08:00_12:00_0.31"

    priceless = TouWindow.parse("08:00_12:00")
    assert priceless is not None
    assert priceless.price is None
    assert priceless.to_api() == "08:00_12:00"


def test_malformed_tou_windows_are_dropped_not_raised():
    assert TouWindow.parse("nonsense") is None
    assert TouWindow.parse_list(["08:00_12:00_0.1", "bad", ""]) == [
        TouWindow(start="08:00", end="12:00", price=0.1)
    ]
    assert TouWindow.parse_list(None) == []


def test_mode_config_derived_properties():
    config = ModeConfig.model_validate(
        {
            "workStatus": "2",
            "dayType": "2",
            "allowChargingXiaGrid": "1",
            "peakTimeList": ["08:00_12:00_0.31"],
            "midPeakTimeList": ["12:00_18:00_0.2"],
            "offPeakTimeList": ["22:00_08:00_0.1"],
        }
    )
    assert config.mode is WorkMode.TIME_OF_USE
    assert config.today_calendar is DayType.NON_WORKDAY
    assert config.grid_charging_allowed
    assert config.has_tou_schedule
    assert len(config.peak_windows) == 1
    assert len(config.mid_peak_windows) == 1
    assert len(config.off_peak_windows) == 1


def test_mode_config_empty_is_inert():
    config = ModeConfig()
    assert config.mode is None
    assert config.today_calendar is None
    assert not config.grid_charging_allowed
    assert not config.has_tou_schedule


def test_reserve_levels_from_config():
    levels = ReserveLevels.from_config(
        ModeConfig.model_validate(
            {
                "selfConsumptioinReserveSoc": "15",
                "backupPowerReserveSoc": "100",
                "evChargerReserveSoc": 50,
                "chargingLimitSoc": 90,
            }
        )
    )
    assert (levels.self_consumption, levels.backup) == (15.0, 100.0)
    assert (levels.ev_charger, levels.charging_limit) == (50.0, 90.0)


def test_from_config_defaults_when_the_device_reports_nothing():
    request = SwitchModeRequest.from_config(ModeConfig.model_validate({"devId": "1"}))
    payload = request.api_dump()
    assert payload["workStatus"] == "1"
    assert payload["selfConsumptioinReserveSoc"] == "5"
    assert payload["backupPowerReserveSoc"] == "50"
    assert payload["allowChargingXiaGrid"] == "1"
    assert payload["activeWeek"] == ["1", "2", "3", "4", "5"]
    assert "evChargerReserveSoc" not in payload


def test_ev_reserve_is_included_when_set():
    request = SwitchModeRequest.from_config(ModeConfig.model_validate({"devId": "1"})).with_changes(
        ev_charger_reserve_soc=40
    )
    assert request.api_dump()["evChargerReserveSoc"] == 40


def test_work_status_accepts_an_enum_or_a_number():
    config = ModeConfig.model_validate({"devId": "1"})
    by_enum = SwitchModeRequest.from_config(config, work_status=WorkMode.BACKUP)
    by_int = SwitchModeRequest.from_config(config, work_status=3)
    assert by_enum.api_dump()["workStatus"] == by_int.api_dump()["workStatus"] == "3"
    assert by_enum.mode is WorkMode.BACKUP


def test_mode_is_none_for_an_unknown_work_status():
    request = SwitchModeRequest.from_config(
        ModeConfig.model_validate({"devId": "1"}), work_status="9"
    )
    assert request.mode is None


def test_set_tou_schedule_replaces_only_what_it_is_given():
    config = ModeConfig.model_validate(
        {"devId": "1", "peakTimeList": ["08:00_12:00_0.3"], "offPeakTimeList": ["22:00_08:00_0.1"]}
    )
    request = SwitchModeRequest.from_config(config).set_tou_schedule(
        peak=[TouWindow(start="09:00", end="11:00", price=0.5)],
        mid_peak=["11:00_12:00_0.4"],
        off_peak=[],
    )
    payload = request.api_dump()
    assert payload["peakTimeList"] == ["09:00_11:00_0.5"]
    assert payload["midPeakTimeList"] == ["11:00_12:00_0.4"]
    assert payload["offPeakTimeList"] == []
    assert payload["peakTimeListNonWorkDay"] == []


def test_set_tou_schedule_with_nothing_changes_nothing():
    config = ModeConfig.model_validate({"devId": "1", "peakTimeList": ["08:00_12:00_0.3"]})
    request = SwitchModeRequest.from_config(config)
    assert request.set_tou_schedule().api_dump() == request.api_dump()


def test_dev_id_can_be_supplied_when_the_config_lacks_one():
    request = SwitchModeRequest.from_config(ModeConfig(), dev_id="99")
    assert request.api_dump()["devId"] == "99"
