"""End-to-end behaviour of the client against canned responses."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from epcube_api import (
    EpCubeAsyncClient,
    EpCubeAuthError,
    EpCubeNotFoundError,
    EpCubeServerError,
    Scope,
    SwitchModeRequest,
    WorkMode,
)

from .conftest import DEV_ID, SN, Recorder

# --- request shaping -------------------------------------------------------


async def test_sends_bearer_token_and_app_user_agent(client, recorder: Recorder):
    await client.account.base()
    headers = recorder.sent("user/user/base").headers
    assert headers["authorization"] == "Bearer test-token"
    assert "ReservoirMonitoring" in headers["user-agent"]


async def test_token_prefix_is_added_when_missing():
    assert EpCubeAsyncClient(token="raw").token == "Bearer raw"
    assert EpCubeAsyncClient(token="Bearer raw").token == "Bearer raw"


async def test_region_selects_the_cluster():
    assert "monitoring-eu" in EpCubeAsyncClient(region="EU").base_url
    assert "epcube-monitoring" in EpCubeAsyncClient(region="us").base_url
    assert "monitoring-jp" in EpCubeAsyncClient(region="JP").base_url


async def test_unknown_region_is_rejected():
    with pytest.raises(ValueError, match="unknown region"):
        EpCubeAsyncClient(region="MARS")


async def test_calling_without_a_token_fails_before_the_request():
    async with EpCubeAsyncClient(region="EU") as bare:
        with pytest.raises(EpCubeAuthError, match="no token"):
            await bare.account.base()


# --- parsing ---------------------------------------------------------------


async def test_live_snapshot_parses_and_coerces(client):
    live = await client.device.home_info(SN)
    assert live.dev_id == DEV_ID
    assert live.battery_soc == 86
    assert live.mode is WorkMode.SELF_CONSUMPTION
    # "1" -> True, and the paired UTC/local timestamps both parse
    assert live.is_online is True
    assert live.is_alert is False
    assert live.def_create_time.hour == 7
    assert live.from_create_time.hour == 9


async def test_device_list_parses_capacity_strings_and_work_param(client):
    devices = await client.device.all()
    ours = next(d for d in devices if d.id == DEV_ID)
    assert ours.system_capacity == 15.0  # from "15.0kWh"
    assert ours.battery_type == 5.0
    assert ours.is_single_phase is True
    assert ours.module_serials == ["1002", "1003", "1004", "1005"]
    # workParam arrives as a JSON string
    assert ours.work_param["evChargerReserveSoc"] == 50


async def test_pv_strings_discovers_inputs_and_converts_to_watts(client):
    pv = await client.device.pv_strings(DEV_ID)
    assert len(pv.strings) == 4
    assert len(pv.active) == 2
    assert pv.strings[0].voltage == 328.20
    assert pv.strings[0].power_w == pytest.approx(250.0)
    assert pv.total_power_w == pytest.approx(610.0)


async def test_outage_duration_comes_from_the_timestamps(client):
    outages = await client.device.outages(DEV_ID)
    assert len(outages) == 1
    assert outages[0].minutes == pytest.approx(7.0)
    assert outages[0].ongoing is False


async def test_mode_config_parses_tou_windows(client):
    config = await client.device.mode(DEV_ID)
    assert config.self_consumption_reserve_soc == "15"
    assert config.grid_charging_allowed is True
    assert config.has_tou_schedule is True
    peak = config.peak_windows[0]
    assert (peak.start, peak.end, peak.price) == ("08:00", "12:00", 0.31)
    assert peak.to_api() == "08:00_12:00_0.31"


async def test_unmodelled_fields_are_kept_not_dropped(client):
    live = await client.device.home_info(SN)
    assert "gridPowerFailureNum" not in live.extras  # this one is modelled
    live_extra = type(live).model_validate({"devId": "1", "somethingNew": 42})
    assert live_extra.extras == {"somethingNew": 42}


# --- time series -----------------------------------------------------------


async def test_series_reports_battery_power_directly(client):
    series = await client.data.series(DEV_ID, Scope.DAY, date(2026, 9, 2))
    assert len(series) == 4
    assert series.granularity == "five minutes"
    latest = series.latest()
    assert latest.node_name == "09:45"
    # kW on the wire; the accessor converts to watts and flips the sign so
    # positive means charging (see test_battery_power_is_positive_when_charging)
    assert latest.reading.battery_power == -0.30
    assert latest.reading.battery_power_w == pytest.approx(300.0)


async def test_series_drops_placeholder_points(client):
    series = await client.data.series(DEV_ID, Scope.DAY, date(2026, 9, 2))
    assert len(series.populated()) == 3  # 04:55 is an all-zero placeholder
    timeline = series.timeline("battery_power_w")
    assert len(timeline) == 3
    assert [t.strftime("%H:%M") for t, _ in timeline] == ["00:00", "00:05", "09:45"]


async def test_series_timestamps_resolve_against_the_queried_date(client):
    series = await client.data.series(DEV_ID, Scope.DAY, date(2026, 9, 2))
    first = series[0].timestamp(date(2026, 9, 2))
    assert first.date() == date(2026, 9, 2)
    assert (first.hour, first.minute) == (0, 0)


async def test_scope_dictates_the_date_format(client, recorder: Recorder):
    when = date(2026, 9, 2)
    await client.data.totals(DEV_ID, Scope.YEAR, when)
    assert recorder.sent("queryDataElectricityV2").url.params["queryDateStr"] == "2026"
    await client.data.totals(DEV_ID, Scope.MONTH, when)
    assert recorder.sent("queryDataElectricityV2").url.params["queryDateStr"] == "2026-09"
    await client.data.totals(DEV_ID, Scope.DAY, when)
    assert recorder.sent("queryDataElectricityV2").url.params["queryDateStr"] == "2026-09-02"


# --- writes: the switchMode reset trap -------------------------------------


async def test_mode_change_sends_every_field(client, recorder: Recorder):
    config = await client.device.mode(DEV_ID)
    await client.device.set_mode(config, WorkMode.BACKUP)
    body = recorder.body("device/switchMode")

    assert body["workStatus"] == "3"
    # everything else has to survive the write, or the device resets it
    assert body["peakTimeList"] == ["08:00_12:00_0.31"]
    assert body["offPeakTimeList"] == ["22:00_08:00_0.12"]
    assert body["selfConsumptioinReserveSoc"] == "15"
    assert body["backupPowerReserveSoc"] == "100"
    assert body["allowChargingXiaGrid"] == "1"


async def test_payload_never_omits_a_field_even_from_an_empty_config(client):
    from epcube_api.models import ModeConfig

    full = SwitchModeRequest.from_config(
        ModeConfig.model_validate({"devId": DEV_ID, "workStatus": "1"})
    )
    complete = SwitchModeRequest.from_config(ModeConfig.model_validate(dict(recorder_mode())))
    assert set(full.api_dump()) == set(complete.api_dump())


def recorder_mode():
    from .conftest import MODE

    return MODE


async def test_active_week_is_coerced_to_strings(client, recorder: Recorder):
    config = await client.device.mode(DEV_ID)
    await client.device.set_mode(config, WorkMode.SELF_CONSUMPTION)
    body = recorder.body("device/switchMode")
    # the API sends ints but rejects them on write
    assert body["activeWeek"] == ["1", "2", "3", "4", "5"]
    assert body["activeWeekNonWorkDay"] == ["6", "7"]


async def test_reserve_change_uses_only_save(client, recorder: Recorder):
    config = await client.device.mode(DEV_ID)
    await client.device.set_reserve_soc(config, self_consumption=25)
    body = recorder.body("device/switchMode")
    assert body["onlySave"] == "1"
    assert body["selfConsumptioinReserveSoc"] == "25"
    assert body["backupPowerReserveSoc"] == "100"  # untouched


async def test_grid_charging_toggle_preserves_the_schedule(client, recorder: Recorder):
    config = await client.device.mode(DEV_ID)
    await client.device.set_grid_charging(config, False)
    body = recorder.body("device/switchMode")
    assert body["allowChargingXiaGrid"] == "0"
    assert body["peakTimeList"] == ["08:00_12:00_0.31"]


async def test_with_changes_rejects_unknown_fields(client):
    config = await client.device.mode(DEV_ID)
    request = SwitchModeRequest.from_config(config)
    with pytest.raises(ValueError, match="unknown switchMode field"):
        request.with_changes(nonsense=1)


async def test_with_changes_accepts_either_spelling(client):
    config = await client.device.mode(DEV_ID)
    request = SwitchModeRequest.from_config(config)
    by_alias = request.with_changes(selfConsumptioinReserveSoc="40")
    by_name = request.with_changes(self_consumption_reserve_soc="40")
    assert by_alias.api_dump() == by_name.api_dump()


async def test_from_config_without_a_device_id_is_refused():
    from epcube_api.models import ModeConfig

    with pytest.raises(ValueError, match="no device id"):
        SwitchModeRequest.from_config(ModeConfig())


# --- error mapping ---------------------------------------------------------


async def test_body_status_401_on_an_http_200_raises(recorder: Recorder):
    """The US and JP clusters report auth failures this way."""
    recorder.overrides["user/user/base"] = httpx.Response(
        200, json={"status": 401, "message": "User token expired"}
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    async with EpCubeAsyncClient(region="US", token="stale", http_client=http) as client:
        with pytest.raises(EpCubeAuthError, match="check the region first"):
            await client.account.base()


async def test_plain_http_401_raises(recorder: Recorder):
    recorder.overrides["user/user/base"] = httpx.Response(401, json={"message": "no"})
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    async with EpCubeAsyncClient(token="stale", http_client=http) as client:
        with pytest.raises(EpCubeAuthError):
            await client.account.base()


async def test_missing_route_raises_not_found(client):
    with pytest.raises(EpCubeNotFoundError):
        await client.raw.get("device/doesNotExist")


async def test_server_error_is_retried_then_raised(recorder: Recorder):
    recorder.overrides["device/netWorkInfo"] = httpx.Response(500, json={"message": "boom"})
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    async with EpCubeAsyncClient(token="t", http_client=http, max_retries=2) as client:
        with pytest.raises(EpCubeServerError):
            await client.device.network(DEV_ID)
    attempts = [r for r in recorder.requests if r.url.path.endswith("netWorkInfo")]
    assert len(attempts) == 2


async def test_probe_reports_failure_without_raising(client):
    ok, detail = await client.probe("device/doesNotExist")
    assert ok is False
    assert "no such route" in detail


# --- snapshot --------------------------------------------------------------


async def test_snapshot_gathers_every_section(client):
    snap = await client.snapshot(SN, include_outages=True)
    assert snap.dev_id == DEV_ID
    assert snap.complete, snap.errors
    assert snap.mode.mode is WorkMode.SELF_CONSUMPTION
    assert snap.detail.model_type.startswith("EP Cube")
    assert snap.summary.rtu_sn == "VD06000325208155"
    assert len(snap.pv.active) == 2
    assert snap.outages[0].minutes == pytest.approx(7.0)


async def test_snapshot_prefers_measured_battery_power(client):
    snap = await client.snapshot(SN)
    # from the series, not derived from the live snapshot's flows
    assert snap.battery_power_w == pytest.approx(300.0)


async def test_snapshot_falls_back_to_derived_battery_power(client):
    snap = await client.snapshot(SN, include_series=False)
    # solar 51 + grid 0 - load 238
    assert snap.battery_power_w == pytest.approx(-187.0)


async def test_snapshot_survives_a_failing_supplementary_route(recorder: Recorder):
    recorder.overrides["device/queryDataElectricityV2"] = httpx.Response(
        500, json={"message": "slow"}
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    async with EpCubeAsyncClient(token="t", http_client=http, max_retries=1) as client:
        snap = await client.snapshot(SN)
    assert snap.live.battery_soc == 86  # live data survived
    assert not snap.complete
    assert "today" in snap.errors


async def test_snapshot_resolves_the_serial_from_the_account(client):
    snap = await client.snapshot()
    assert snap.dev_id == DEV_ID


# --- sign and source conventions --------------------------------------------


async def test_battery_power_is_positive_when_charging(client):
    """The API sends negative for charging; everything here uses positive.

    Established from the energy balance on a real system: solar + grid - load +
    battery == 0 only holds with the API's negative-is-charging convention.
    """
    series = await client.data.series(DEV_ID, Scope.DAY, date(2026, 9, 2))
    reading = series.latest().reading
    assert reading.battery_power == -0.30  # raw, as sent
    assert reading.battery_power_w == pytest.approx(300.0)  # normalised


async def test_snapshot_prefers_a_trustworthy_solar_source(client):
    snap = await client.snapshot(SN)
    # the series agrees with the per-string endpoint; live.solar_power does not
    assert snap.solar_power_source == "series"
    assert snap.solar_power_w == pytest.approx(610.0)
    assert snap.live.solar_power == 51.0


async def test_solar_falls_back_to_pv_strings_without_a_series(client):
    snap = await client.snapshot(SN, include_series=False)
    assert snap.solar_power_source == "pv_strings"
    assert snap.solar_power_w == pytest.approx(610.0)
