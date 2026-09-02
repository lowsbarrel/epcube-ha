"""Model coercions, derived properties and the request builders."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from epcube_api import (
    DeviceDetail,
    DeviceSummary,
    EnergySeries,
    EnergyTotals,
    LiveSnapshot,
    ModeConfig,
    OutageEvent,
    PvString,
    PvStrings,
    Region,
    Scope,
    SeriesPoint,
    SwitchModeRequest,
    TouWindow,
    Warranty,
    WorkMode,
)
from epcube_api.const import DayType, SystemStatus
from epcube_api.models.mode import ReserveLevels

# --- coercions -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.70", 0.7),
        ("15kWh", 15.0),
        ("15.0kWh", 15.0),
        ("1,5", 1.5),
        (12, 12.0),
        ("", None),
        (None, None),
        ("-", None),
        ("abc", None),
        ("-3.5", -3.5),
    ],
)
def test_float_coercion(raw, expected):
    assert LiveSnapshot.model_validate({"solarPower": raw}).solar_power == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        (1, True),
        ("true", True),
        ("YES", True),
        (True, True),
        ("0", False),
        (0, False),
        ("false", False),
        ("no", False),
        ("", None),
        (None, None),
    ],
)
def test_bool_coercion(raw, expected):
    assert LiveSnapshot.model_validate({"isOnline": raw}).is_online == expected


def test_unrecognised_values_become_none_not_validation_errors():
    """One odd field must not fail the whole response.

    The coercers return None rather than passing the raw value to pydantic,
    which would reject it and take the entire snapshot down with it.
    """
    assert LiveSnapshot.model_validate({"isOnline": "maybe"}).is_online is None
    assert LiveSnapshot.model_validate({"defCreateTime": "not a date"}).def_create_time is None
    assert ModeConfig.model_validate({"devId": ["a", "list"]}).dev_id is None
    assert ModeConfig.model_validate({"activeWeek": "not a list"}).active_week == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-09-02 07:19:05", datetime(2026, 9, 2, 7, 19, 5)),
        ("2026-09-01 12:19", datetime(2026, 9, 1, 12, 19)),
        ("2026-09-02T07:19:05", datetime(2026, 9, 2, 7, 19, 5)),
        ("2026-09-02", datetime(2026, 9, 2)),
        ("", None),
    ],
)
def test_datetime_coercion(raw, expected):
    assert LiveSnapshot.model_validate({"defCreateTime": raw}).def_create_time == expected


def test_datetime_coercion_from_epoch():
    seconds = LiveSnapshot.model_validate({"defCreateTime": 1756800000}).def_create_time
    millis = LiveSnapshot.model_validate({"defCreateTime": 1756800000000}).def_create_time
    assert seconds == millis


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(1, "1"), ("1", "1"), (1.0, "1"), (1.5, "1.5"), (True, "1"), (False, "0"), ("", None)],
)
def test_str_coercion(raw, expected):
    assert ModeConfig.model_validate({"devId": raw}).dev_id == expected


def test_str_list_coercion():
    config = ModeConfig.model_validate({"activeWeek": [1, 2, 3]})
    assert config.active_week == ["1", "2", "3"]
    assert ModeConfig.model_validate({"activeWeek": None}).active_week == []
    assert ModeConfig.model_validate({}).active_week == []


def test_int_coercion_of_nonsense_is_none():
    assert LiveSnapshot.model_validate({"batterySoc": "abc"}).battery_soc is None


def test_api_dump_uses_the_wire_names():
    dumped = LiveSnapshot.model_validate({"devId": "1", "backUpPower": 5}).api_dump()
    assert dumped["devId"] == "1"
    assert dumped["backUpPower"] == 5.0


# --- enums -----------------------------------------------------------------


def test_region_parsing_and_urls():
    assert Region.parse("eu") is Region.EU
    assert Region.parse(Region.JP) is Region.JP
    assert "epcube-monitoring" in Region.US.base_url
    with pytest.raises(ValueError, match="unknown region"):
        Region.parse("nowhere")


def test_scope_date_formats_and_granularity():
    when = date(2026, 9, 2)
    assert Scope.DAY.format_date(when) == "2026-09-02"
    assert Scope.MONTH.format_date(when) == "2026-09"
    assert Scope.YEAR.format_date(when) == "2026"
    assert Scope.LIFETIME.format_date(when) == "2026"
    assert Scope.DAY.series_granularity == "five minutes"
    assert Scope.LIFETIME.series_granularity == "one year"


def test_work_mode_labels():
    assert WorkMode.SELF_CONSUMPTION.label == "Self-consumption"
    assert WorkMode.TIME_OF_USE.label == "Time of Use"
    assert WorkMode.BACKUP.label == "Backup"


def test_status_enums_exist():
    assert SystemStatus.ONLINE == 4
    assert DayType.WORKDAY == 1


# --- live snapshot ---------------------------------------------------------


def test_live_mode_is_none_for_an_unknown_value():
    assert LiveSnapshot.model_validate({"workStatus": "9"}).mode is None
    assert LiveSnapshot.model_validate({}).mode is None


def test_load_and_battery_power_need_their_inputs():
    empty = LiveSnapshot.model_validate({})
    assert empty.load_power is None
    assert empty.battery_power is None

    partial = LiveSnapshot.model_validate({"backUpPower": 100})
    assert partial.load_power == 100
    # still no solar or grid, so nothing to derive from
    assert partial.battery_power is None

    full = LiveSnapshot.model_validate(
        {"solarPower": 1000, "gridPower": 0, "backUpPower": 100, "nonBackUpPower": 50}
    )
    assert full.load_power == 150
    assert full.battery_power == 850


# --- mode config -----------------------------------------------------------


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


# --- device ----------------------------------------------------------------


def test_device_summary_edge_cases():
    empty = DeviceSummary()
    assert empty.module_serials == []
    assert empty.is_single_phase is None
    assert empty.work_param == {}

    three_phase = DeviceSummary.model_validate({"deviceSystemType": "3Phase"})
    assert three_phase.is_single_phase is False


@pytest.mark.parametrize("raw", ["", "not json", "[1,2]", None])
def test_work_param_survives_junk(raw):
    assert DeviceSummary.model_validate({"workParam": raw}).work_param == {}


def test_warranty_years():
    warranty = Warranty.model_validate(
        {"activationDate": "2026-09-01", "usageEndDate": "2036-09-01"}
    )
    assert warranty.years == pytest.approx(10.0, abs=0.02)
    assert Warranty().years is None


def test_outage_without_an_end_is_ongoing():
    ongoing = OutageEvent.model_validate({"startTime": "2026-09-01 12:19"})
    assert ongoing.ongoing
    assert ongoing.minutes is None


def test_device_detail_allows_the_model_field_name():
    detail = DeviceDetail.model_validate({"modelType": "EP Cube", "batteryCapacity": "15kWh"})
    assert detail.model_type == "EP Cube"
    assert detail.battery_capacity == 15.0


# --- pv strings ------------------------------------------------------------


def test_pv_strings_parse_from_either_shape():
    record = {"pv1Voltage": "300", "pv1Current": "1.0", "pv1Power": "0.3"}
    from_list = PvStrings.from_api([record])
    from_dict = PvStrings.from_api(record)
    assert from_list.strings == from_dict.strings
    assert from_list.strings[0].power_w == pytest.approx(300.0)


def test_pv_strings_from_nothing():
    for payload in ([], None, [None], {}):
        assert PvStrings.from_api(payload).strings == []


def test_pv_string_with_unparsable_values():
    parsed = PvStrings.from_api([{"pv1Voltage": "abc", "pv1Current": "", "pv1Power": None}])
    assert parsed.strings[0].voltage is None
    assert parsed.strings[0].power_w is None
    assert not parsed.strings[0].is_active
    assert parsed.total_power_w == 0.0


def test_pv_string_activity():
    assert PvString(index=1, voltage=300.0).is_active
    assert PvString(index=1, current=1.0).is_active
    assert not PvString(index=1, voltage=0.0, current=0.0).is_active


# --- energy ----------------------------------------------------------------


def test_energy_totals_net_grid():
    totals = EnergyTotals.model_validate({"gridElectricityFrom": 5.0, "gridElectricityTo": 2.0})
    assert totals.net_grid == 3.0
    assert EnergyTotals().net_grid is None


def test_series_reading_watt_conversions():
    reading = EnergySeries.from_api(
        [
            {
                "nodeName": "10:00",
                "scopeType": "1",
                "nodeVo": {
                    "id": "1",
                    "solarPower": 1.0,
                    "gridPower": -0.5,
                    "batteryPower": -0.25,
                    "backUpPower": 0.1,
                    "nonBackUpPower": 0.2,
                },
            }
        ],
        scope=Scope.DAY,
        queried=date(2026, 9, 2),
    )[0].reading
    assert reading.solar_power_w == 1000.0
    assert reading.grid_power_w == -500.0
    assert reading.battery_power_w == 250.0  # sign flipped: positive is charging
    assert reading.load_power_w == pytest.approx(300.0)


def test_series_reading_without_values():
    from epcube_api.models.energy import SeriesReading

    blank = SeriesReading()
    assert blank.solar_power_w is None
    assert blank.battery_power_w is None
    assert blank.load_power_w is None
    assert blank.is_empty


def test_series_point_timestamps_per_scope():
    for scope, label, expected in (
        (Scope.DAY, "09:45", datetime(2026, 9, 2, 9, 45)),
        (Scope.MONTH, "07", datetime(2026, 9, 7)),
        (Scope.YEAR, "03", datetime(2026, 3, 1)),
        (Scope.LIFETIME, "2024", datetime(2024, 1, 1)),
    ):
        point = SeriesPoint.model_validate(
            {"nodeName": label, "scopeType": str(int(scope)), "nodeVo": {}}
        )
        assert point.timestamp(date(2026, 9, 2)) == expected


def test_series_point_handles_the_end_of_day_label():
    point = SeriesPoint.model_validate({"nodeName": "24:00", "scopeType": "1", "nodeVo": {}})
    assert point.timestamp(date(2026, 9, 2)) == datetime(2026, 9, 3)


@pytest.mark.parametrize(
    "payload",
    [
        {"nodeName": "", "scopeType": "1"},
        {"nodeName": "09:45", "scopeType": "bad"},
        {"nodeName": "not-a-time", "scopeType": "1"},
        {"nodeName": "99", "scopeType": "2"},
    ],
)
def test_series_point_timestamp_is_none_when_unresolvable(payload):
    assert SeriesPoint.model_validate(payload).timestamp(date(2026, 9, 2)) is None


def test_series_point_accepts_a_datetime_as_the_queried_value():
    point = SeriesPoint.model_validate({"nodeName": "09:45", "scopeType": "1"})
    assert point.timestamp(datetime(2026, 9, 2, 3, 0)) == datetime(2026, 9, 2, 9, 45)


def test_empty_series_has_no_latest():
    series = EnergySeries.from_api(None, scope=Scope.DAY, queried=date(2026, 9, 2))
    assert len(series) == 0
    assert series.latest() is None
    assert series.timeline("battery_power_w") == []
    assert series.granularity == "five minutes"


def test_series_timeline_skips_unknown_fields():
    series = EnergySeries.from_api(
        [{"nodeName": "10:00", "scopeType": "1", "nodeVo": {"id": "1", "solarPower": 1.0}}],
        scope=Scope.DAY,
        queried=date(2026, 9, 2),
    )
    assert series.timeline("does_not_exist") == []


# --- switch mode request ---------------------------------------------------


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
    # untouched lists survive
    assert payload["peakTimeListNonWorkDay"] == []


def test_set_tou_schedule_with_nothing_changes_nothing():
    config = ModeConfig.model_validate({"devId": "1", "peakTimeList": ["08:00_12:00_0.3"]})
    request = SwitchModeRequest.from_config(config)
    assert request.set_tou_schedule().api_dump() == request.api_dump()


def test_dev_id_can_be_supplied_when_the_config_lacks_one():
    request = SwitchModeRequest.from_config(ModeConfig(), dev_id="99")
    assert request.api_dump()["devId"] == "99"


def test_unusable_container_values_coerce_to_none():
    """A list where a number is expected must not fail the whole response."""
    assert LiveSnapshot.model_validate({"solarPower": [1, 2]}).solar_power is None
    assert LiveSnapshot.model_validate({"batterySoc": {"a": 1}}).battery_soc is None


def test_registry_lookup_and_coverage():
    from epcube_api.registry import ROUTES, Verified, by_group, coverage, find

    stats = coverage()
    assert stats["total"] == len(ROUTES)
    assert 0 < stats["wrapped"] <= stats["total"]
    assert 0 < stats["verified"] <= stats["wrapped"]

    live = find("device/homeDeviceInfo")
    assert live is not None
    assert live.wrapped
    assert live.wrapper == "device.home_info"
    assert live.verified is Verified.WORKING
    assert find("device/doesNotExist") is None

    groups = by_group()
    assert "device" in groups
    assert all(r.group == "device" for r in groups["device"])


def test_coercion_branches_for_numeric_inputs():
    """Numbers reach the coercers as ints and floats, not only as strings."""
    assert LiveSnapshot.model_validate({"isOnline": 2.5}).is_online is True
    assert LiveSnapshot.model_validate({"isOnline": 0.0}).is_online is False
    assert LiveSnapshot.model_validate({"defCreateTime": 0}).def_create_time is not None
    assert ModeConfig.model_validate({"devId": True}).dev_id == "1"


def test_api_error_without_a_path_or_status():
    from epcube_api import EpCubeAPIError

    bare = EpCubeAPIError("something went wrong")
    assert str(bare) == "something went wrong"
    with_path = EpCubeAPIError("nope", path="device/x")
    assert "device/x" in str(with_path)


def test_snapshot_ignores_a_series_whose_latest_point_lacks_the_value():
    from epcube_api import EnergySeries, LiveSnapshot, Scope
    from epcube_api.models.snapshot import Snapshot

    # A populated point (it has an id) that still carries no power readings.
    series = EnergySeries.from_api(
        [{"nodeName": "10:00", "scopeType": "1", "nodeVo": {"id": "1", "batterySoc": 50}}],
        scope=Scope.DAY,
        queried=date(2026, 9, 2),
    )
    snap = Snapshot(
        dev_id="1",
        live=LiveSnapshot.model_validate({"solarPower": 100, "gridPower": 0, "backUpPower": 10}),
        series=series,
    )
    # falls back to the derived value rather than reporting None
    assert snap.battery_power_w == 90
    assert snap.solar_power_w == 100


def test_coercers_reject_containers_across_every_type():
    """A list or dict where a scalar belongs must degrade to None, not raise."""
    assert LiveSnapshot.model_validate({"isOnline": ["x"]}).is_online is None
    assert LiveSnapshot.model_validate({"defCreateTime": ["x"]}).def_create_time is None
