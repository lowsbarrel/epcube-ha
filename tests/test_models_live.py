from __future__ import annotations

from datetime import date

import pytest

from epcube_api import EnergySeries, LiveSnapshot, Scope
from epcube_api.models.snapshot import Snapshot


def test_live_mode_is_none_for_an_unknown_value():
    assert LiveSnapshot.model_validate({"workStatus": "9"}).mode is None
    assert LiveSnapshot.model_validate({}).mode is None


def test_load_and_battery_power_need_their_inputs():
    empty = LiveSnapshot.model_validate({})
    assert empty.load_power is None
    assert empty.battery_power is None

    partial = LiveSnapshot.model_validate({"backUpPower": 100})
    assert partial.load_power == 100
    assert partial.battery_power is None

    full = LiveSnapshot.model_validate(
        {"solarPower": 1000, "gridPower": 0, "backUpPower": 100, "nonBackUpPower": 50}
    )
    assert full.load_power == 150
    assert full.battery_power == 850


def test_load_electricity_sums_backup_and_non_backup():
    assert LiveSnapshot.model_validate({}).load_electricity is None
    # One circuit present is enough; the absent one counts as zero.
    assert LiveSnapshot.model_validate({"backUpElectricity": 7.06}).load_electricity == 7.06
    full = LiveSnapshot.model_validate({"backUpElectricity": 7.06, "nonBackUpElectricity": 1.2})
    assert full.load_electricity == pytest.approx(8.26)


def test_snapshot_ignores_a_series_whose_latest_point_lacks_the_value():
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
    assert snap.battery_power_w == 90
    assert snap.solar_power_w == 100
