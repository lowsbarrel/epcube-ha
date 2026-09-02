"""Every endpoint group: the route it calls and the parameters it sends."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from epcube_api import EpCubeAsyncClient, EpCubeError, Scope, WorkMode
from epcube_api.models import ModeConfig

from .conftest import DEV_ID, SN, Recorder


class Echo:
    """Answers every route with a fixed body, and records what was asked."""

    def __init__(self, data=None) -> None:
        self.data = {} if data is None else data
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json={"status": 200, "data": self.data})

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def path(self) -> str:
        return self.last.url.path.split("/api/", 1)[-1]

    def params(self) -> dict[str, str]:
        return dict(self.last.url.params)


@pytest.fixture
async def echo():
    return Echo()


@pytest.fixture
async def probe(echo: Echo):
    http = httpx.AsyncClient(transport=httpx.MockTransport(echo.handler))
    async with EpCubeAsyncClient(region="EU", token="t", http_client=http) as client:
        yield client
    await http.aclose()


# --- account and public ----------------------------------------------------


async def test_account_routes(probe, echo: Echo):
    await probe.account.firmware_info()
    assert echo.path() == "user/user/queryFirmwareInfo"

    await probe.account.service_data()
    assert echo.path() == "user/user/serviceData"

    await probe.account.set_language("it")
    assert echo.path() == "user/user/saveUserLanguage"

    await probe.account.edit_profile(nickName="x")
    assert echo.path() == "user/user/editUserInfo"

    await probe.account.change_password("old", "new")
    assert echo.path() == "user/user/changePwdByOld"


async def test_public_routes_send_no_token(probe, echo: Echo):
    await probe.public.captcha("uid")
    assert echo.path() == "open/common/captcha/get"
    assert "authorization" not in echo.last.headers

    await probe.public.verify_captcha("uid", "tok", "point")
    assert echo.path() == "open/common/captcha/check"

    await probe.public.login("user", "pass", "verification")
    assert echo.path() == "open/common/login"

    await probe.public.request_email_code("a@b.c")
    assert echo.path() == "open/common/getEmailCode"

    await probe.public.app_version()
    assert echo.path() == "open/version/update"


async def test_public_endpoints_work_without_a_token():
    echo = Echo()
    http = httpx.AsyncClient(transport=httpx.MockTransport(echo.handler))
    async with EpCubeAsyncClient(region="EU", http_client=http) as client:
        await client.public.app_version()
    assert echo.path() == "open/version/update"
    await http.aclose()


# --- device ----------------------------------------------------------------


async def test_device_read_routes(probe, echo: Echo):
    await probe.device.firmware_version(DEV_ID)
    assert echo.path() == "device/getDevPcsVersion"

    await probe.device.check_upgrade(DEV_ID)
    assert echo.path() == "device/checkUpgrade"

    await probe.device.warranty(DEV_ID)
    assert echo.path() == "device/getWarranty"

    await probe.device.home_info(SN, day=date(2026, 1, 2))
    assert echo.params()["dayMonthYearFormat"] == "2026-01-02"


async def test_device_list_returns_empty_for_a_non_list_body():
    echo = Echo(data={"not": "a list"})
    http = httpx.AsyncClient(transport=httpx.MockTransport(echo.handler))
    async with EpCubeAsyncClient(region="EU", token="t", http_client=http) as client:
        assert await client.device.all() == []
    await http.aclose()


async def test_set_reserve_soc_requires_something_to_change(client):
    config = await client.device.mode(DEV_ID)
    with pytest.raises(ValueError, match="nothing to change"):
        await client.device.set_reserve_soc(config)


async def test_set_reserve_soc_can_change_both(client, recorder: Recorder):
    config = await client.device.mode(DEV_ID)
    await client.device.set_reserve_soc(config, self_consumption=20, backup=80)
    body = recorder.body("device/switchMode")
    assert body["selfConsumptioinReserveSoc"] == "20"
    assert body["backupPowerReserveSoc"] == "80"


async def test_switch_mode_accepts_a_prebuilt_request(client, recorder: Recorder):
    from epcube_api import SwitchModeRequest

    config = await client.device.mode(DEV_ID)
    request = SwitchModeRequest.from_config(config, work_status=WorkMode.TIME_OF_USE)
    await client.device.switch_mode(request)
    assert recorder.body("device/switchMode")["workStatus"] == "2"


# --- data ------------------------------------------------------------------


async def test_data_routes(probe, echo: Echo):
    await probe.data.price_series(DEV_ID, Scope.MONTH, date(2026, 9, 2))
    assert echo.path() == "device/queryPriceDataGraphV2"
    assert echo.params()["queryDateStr"] == "2026-09"

    await probe.data.earnings(DEV_ID)
    assert echo.path() == "device/getEarningsConfig"


async def test_scope_accepts_a_bare_int(probe, echo: Echo):
    await probe.data.totals(DEV_ID, 3, date(2026, 9, 2))
    assert echo.params()["scopeType"] == "3"
    assert echo.params()["queryDateStr"] == "2026"


async def test_series_defaults_to_today(probe, echo: Echo):
    await probe.data.series(DEV_ID)
    assert echo.params()["queryDateStr"] == date.today().strftime("%Y-%m-%d")


# --- the untested families -------------------------------------------------


async def test_vpp_routes(probe, echo: Echo):
    for call, expected in (
        (probe.vpp.user_info(), "vpp/userInfo"),
        (probe.vpp.programs(), "vpp/allPrograms"),
        (probe.vpp.site_programs("s1"), "vpp/site/programs"),
        (probe.vpp.enrollments(), "vpp/enrollments"),
        (probe.vpp.enrollment_status(), "vpp/globalEnrollmentStatus"),
        (probe.vpp.events(), "vpp/events"),
        (probe.vpp.global_soc(), "vpp/flip/getGlobalSoc"),
    ):
        await call
        assert echo.path() == expected


async def test_smart_breaker_routes(probe, echo: Echo):
    await probe.breaker.graph(DEV_ID)
    assert echo.path() == "smartBreaker/queryDataGraph"
    await probe.breaker.add(name="x")
    assert echo.path() == "smartBreaker/addDevice"
    await probe.breaker.update(name="x")
    assert echo.path() == "smartBreaker/updateDevice"
    await probe.breaker.save_settings(a=1)
    assert echo.path() == "smartBreaker/saveSettingData"


async def test_message_routes(probe, echo: Echo):
    await probe.messages.list()
    assert echo.path() == "message/messageList"
    await probe.messages.types()
    assert echo.path() == "message/messageTypeInfo"
    await probe.messages.read_all()
    assert echo.path() == "message/readAll"
    await probe.messages.set_push(True)
    assert echo.path() == "message/changeMsgPushStatus"
    await probe.messages.set_push(False)
    assert echo.path() == "message/changeMsgPushStatus"


async def test_support_routes(probe, echo: Echo):
    await probe.support.help_list()
    assert echo.path() == "help/helpList"
    await probe.support.help_detail("42")
    assert echo.path() == "help/helpDetail"
    await probe.support.install_log()
    assert echo.path() == "installLog/queryInstallLogInfo"
    await probe.support.weather()
    assert echo.path() == "weatherApi/weather/getWeather"


async def test_raw_endpoints_reach_anything(probe, echo: Echo):
    await probe.raw.get("device/anything", devId=DEV_ID)
    assert echo.path() == "device/anything"
    await probe.raw.post("device/anything", body={"a": 1})
    assert echo.path() == "device/anything"


async def test_probe_returns_the_payload_on_success(probe):
    ok, payload = await probe.probe("device/anything")
    assert ok
    assert payload == {}


# --- resolution ------------------------------------------------------------


async def test_resolve_device_uses_the_supplied_serial(client, recorder: Recorder):
    sn, dev_id, live = await client.resolve_device(SN)
    assert (sn, dev_id) == (SN, DEV_ID)
    assert live.dev_id == DEV_ID
    # no account lookup was needed
    assert not any(r.url.path.endswith("user/user/base") for r in recorder.requests)


async def test_resolve_device_without_a_serial_anywhere(recorder: Recorder):
    recorder.overrides["user/user/base"] = httpx.Response(
        200, json={"status": 200, "data": {"defDevSgSn": None}}
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    async with EpCubeAsyncClient(region="EU", token="t", http_client=http) as client:
        with pytest.raises(EpCubeError, match="no default plant serial"):
            await client.resolve_device()
    await http.aclose()


async def test_resolve_device_without_a_dev_id(recorder: Recorder):
    recorder.overrides["device/homeDeviceInfo"] = httpx.Response(
        200, json={"status": 200, "data": {"batterySoc": 50}}
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    async with EpCubeAsyncClient(region="EU", token="t", http_client=http) as client:
        with pytest.raises(EpCubeError, match="no devId"):
            await client.resolve_device(SN)
    await http.aclose()


async def test_snapshot_without_optional_sections(client):
    snap = await client.snapshot(SN, include_totals=False, include_series=False)
    assert snap.today is None
    assert snap.series is None
    assert snap.outages == []
    assert snap.complete


async def test_snapshot_records_a_failing_device_list(recorder: Recorder):
    recorder.overrides["device/deviceList"] = httpx.Response(500, json={"message": "no"})
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    async with EpCubeAsyncClient(region="EU", token="t", http_client=http, max_retries=1) as client:
        snap = await client.snapshot(SN)
    assert "summary" in snap.errors
    assert snap.summary is None
    await http.aclose()


async def test_snapshot_summary_line_and_helpers(client):
    snap = await client.snapshot(SN)
    line = snap.summary_line()
    assert "SoC" in line and "Self-consumption" in line
    assert snap.battery_soc == 86
    assert snap.fetched_at is not None


async def test_summary_line_survives_an_empty_snapshot():
    from epcube_api import LiveSnapshot
    from epcube_api.models.snapshot import Snapshot

    snap = Snapshot(dev_id="1", live=LiveSnapshot())
    assert snap.summary_line() == "SoC ?"
    assert snap.battery_power_w is None
    assert snap.solar_power_w is None
    assert snap.solar_power_source == "live"


async def test_solar_source_falls_back_to_live_when_pv_is_idle():
    from epcube_api import LiveSnapshot, PvString, PvStrings
    from epcube_api.models.snapshot import Snapshot

    snap = Snapshot(
        dev_id="1",
        live=LiveSnapshot.model_validate({"solarPower": 42}),
        pv=PvStrings(strings=[PvString(index=1, voltage=0.0, current=0.0)]),
    )
    assert snap.solar_power_source == "live"
    assert snap.solar_power_w == 42


async def test_mode_config_without_a_device_id_is_refused(client):
    with pytest.raises(ValueError, match="no device id"):
        await client.device.set_mode(ModeConfig(), WorkMode.BACKUP)


async def test_the_client_exposes_its_call_history(client):
    await client.account.base()
    assert [call.path for call in client.calls] == ["user/user/base"]
    assert client.calls[0].ok


# --- tou schedule ----------------------------------------------------------


async def test_set_tou_schedule_saves_without_changing_mode(client, recorder: Recorder):
    from epcube_api import TouWindow

    config = await client.device.mode(DEV_ID)
    await client.device.set_tou_schedule(
        config,
        peak=[TouWindow(start="09:00", end="11:00", price=0.5)],
        off_peak=["23:00_07:00_0.1"],
    )
    body = recorder.body("device/switchMode")
    assert body["onlySave"] == "1"
    assert body["workStatus"] == "1"  # unchanged
    assert body["peakTimeList"] == ["09:00_11:00_0.5"]
    assert body["offPeakTimeList"] == ["23:00_07:00_0.1"]
    # lists not mentioned keep what the device had
    assert body["midPeakTimeList"] == []


async def test_set_tou_schedule_can_also_switch_mode(client, recorder: Recorder):
    config = await client.device.mode(DEV_ID)
    await client.device.set_tou_schedule(config, peak=["08:00_12:00_0.3"], apply=True)
    body = recorder.body("device/switchMode")
    assert body["onlySave"] == "0"
    assert body["workStatus"] == "2"


async def test_set_tou_schedule_preserves_the_reserve_levels(client, recorder: Recorder):
    config = await client.device.mode(DEV_ID)
    await client.device.set_tou_schedule(config, peak=[])
    body = recorder.body("device/switchMode")
    assert body["selfConsumptioinReserveSoc"] == "15"
    assert body["backupPowerReserveSoc"] == "100"
