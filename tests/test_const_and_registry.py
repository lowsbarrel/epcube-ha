from __future__ import annotations

from datetime import date

import pytest

from epcube_api import EpCubeAPIError, Region, Scope, WorkMode
from epcube_api.const import DayType, SystemStatus
from epcube_api.registry import ROUTES, Verified, by_group, coverage, find


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


def test_registry_lookup_and_coverage():
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


def test_api_error_without_a_path_or_status():
    bare = EpCubeAPIError("something went wrong")
    assert str(bare) == "something went wrong"
    with_path = EpCubeAPIError("nope", path="device/x")
    assert "device/x" in str(with_path)
