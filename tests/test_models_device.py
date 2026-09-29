from __future__ import annotations

import pytest

from epcube_api import DeviceDetail, DeviceSummary, OutageEvent, Warranty


def test_device_summary_edge_cases():
    empty = DeviceSummary()
    assert empty.module_serials == []
    assert empty.is_single_phase is None
    assert empty.work_param == {}

    three_phase = DeviceSummary.model_validate({"deviceSystemType": "3Phase"})
    assert three_phase.is_single_phase is False


@pytest.mark.parametrize("raw", ["", "not json", "[1,2]", None])
def test_work_param_survives_junk(raw: object):
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
