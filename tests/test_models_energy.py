from __future__ import annotations

from datetime import date, datetime

import pytest

from epcube_api import (
    EnergySeries,
    EnergyTotals,
    PvString,
    PvStrings,
    Scope,
    SeriesPoint,
)
from epcube_api.models.energy import SeriesReading


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
    # The wire carries kW and negative-is-charging; the accessor flips the sign.
    assert reading.battery_power_w == 250.0
    assert reading.load_power_w == pytest.approx(300.0)


def test_series_reading_without_values():
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
def test_series_point_timestamp_is_none_when_unresolvable(payload: dict[str, object]):
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


def test_pv_strings_parse_from_either_shape():
    record = {"pv1Voltage": "300", "pv1Current": "1.0", "pv1Power": "0.3"}
    from_list = PvStrings.from_api([record])
    from_dict = PvStrings.from_api(record)
    assert from_list.strings == from_dict.strings
    assert from_list.strings[0].power_w == pytest.approx(300.0)


def test_pv_strings_from_nothing():
    payloads: tuple[object, ...] = ([], None, [None], {})
    for payload in payloads:
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
