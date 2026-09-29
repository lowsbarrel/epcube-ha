from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from epcube_api import EpCubeAsyncClient

DEV_ID = "1234"
SN = "100100000000000000001"

LIVE: dict[str, Any] = {
    "devId": DEV_ID,
    "status": "1",
    "isOnline": "1",
    "signalLevel": 4,
    "workStatus": "1",
    "batterySoc": 86,
    "batteryCurrentElectricity": 12.99,
    "gridPowerFailureNum": 15,
    "gridPower": 0,
    "solarPower": 51.0,
    "solarElectricity": 0.76,
    "backUpPower": 238.0,
    "backUpElectricity": 1.81,
    "nonBackUpPower": 0,
    "batteryPackNum": 3,
    "defCreateTime": "2026-09-02 07:19:05",
    "defTimeZone": "UTC",
    "fromCreateTime": "2026-09-02 09:19:05",
    "fromTimeZone": "Europe/Rome",
    "unitDefault": "€",
    "isAlert": "0",
    "isFault": "0",
}

MODE: dict[str, Any] = {
    "devId": DEV_ID,
    "workStatus": "1",
    "onlySave": "1",
    "backupPowerReserveSoc": "100",
    # The API's own misspelling; the correctly-spelled key is ignored on write.
    "selfConsumptioinReserveSoc": "15",
    "allowChargingXiaGrid": "1",
    "activeWeek": [1, 2, 3, 4, 5],
    "activeWeekNonWorkDay": [6, 7],
    "dayLightActiveWeek": [1, 2, 3, 4, 5],
    "dayLightActiveWeekNonWorkDay": [6, 7],
    "dayLightSavingTime": False,
    "evChargerReserveSoc": 50,
    "chargingLimitSoc": 100,
    "touType": 0,
    "peakTimeList": ["08:00_12:00_0.31"],
    "midPeakTimeList": [],
    "offPeakTimeList": ["22:00_08:00_0.12"],
}

DEVICE_LIST: list[dict[str, Any]] = [
    {
        "id": DEV_ID,
        "sgSn": SN,
        "rtuSn": "VD00000000000001",
        "snItems": "1002,1003,1004,1005",
        "softwareVersion": "V1.3.0",
        "systemCapacity": "15.0kWh",
        "batteryType": "5.0kWh",
        "deviceSystemType": "1Phase",
        "isParallel": "0",
        "lat": "45.0000",
        "lon": "10.0000",
        "lastConnectTime": "2026-09-02 07:19:05",
        "workParam": json.dumps({"weatherWatch": "0", "evChargerReserveSoc": 50}),
    },
    {"id": "111111", "rtuSn": "OTHER"},
]

DETAIL = {
    "name": "Test Owner",
    "sgSn": SN,
    "modelType": "EP Cube HES-EU2-S7-15G",
    "batteryCapacity": "15kWh",
    "activationData": "2026-09-01",
    "warrantyData": "2036-09-01",
}

PV = [
    {
        "pv1Voltage": "328.20",
        "pv1Current": "0.70",
        "pv1Power": "0.25",
        "pv2Voltage": "319.70",
        "pv2Current": "1.10",
        "pv2Power": "0.36",
        "pv3Voltage": "0.00",
        "pv3Current": "0.00",
        "pv3Power": "0.00",
        "pv4Voltage": "0.00",
        "pv4Current": "0.00",
        "pv4Power": "0.00",
    }
]

OUTAGES = [
    {
        "id": "1000001",
        "devId": DEV_ID,
        "duration": "7m",
        "startTime": "2026-09-01 12:19",
        "endTime": "2026-09-01 12:26",
    }
]

TOTALS = {
    "gridElectricityFrom": 0.5,
    "gridElectricityTo": 0.0,
    "solarElectricity": 0.76,
    "backUpElectricity": 1.81,
    "selfHelpRate": 73.0,
    "hasValue": 1,
}


def _series_point(label: str, *, soc: int, battery_kw: float, populated: bool = True):
    if not populated:
        reading = dict.fromkeys(
            (
                "batterySoc",
                "batteryPower",
                "solarPower",
                "gridPower",
                "backUpPower",
                "nonBackUpPower",
                "solarElectricity",
            ),
            0.0,
        ) | {"hasValue": 0}
        return {"nodeName": label, "scopeType": "1", "nodeVo": reading}

    reading = {
        "id": f"10000{abs(hash(label)) % 100000}",
        "batterySoc": soc,
        "batteryPower": battery_kw,
        "solarPower": 0.61,
        "gridPower": 0.0,
        "backUpPower": 0.27,
        "nonBackUpPower": 0.0,
        "solarElectricity": 36.17,
        # 0 even on populated points - see SeriesReading.is_empty
        "hasValue": 0,
    }
    return {"nodeName": label, "scopeType": "1", "nodeVo": reading}


SERIES = [
    _series_point("00:00", soc=90, battery_kw=-0.03),
    _series_point("00:05", soc=90, battery_kw=-0.05),
    _series_point("04:55", soc=0, battery_kw=0.0, populated=False),
    _series_point("09:45", soc=85, battery_kw=-0.30),
]

NETWORK = {
    "networking": 1,
    "wifiName": "home-wifi",
    "wifiStatus": 4,
    "wifiStatusStr": "collegato",
    "signalLevel": 4,
}

ROUTES: dict[str, Any] = {
    "user/user/base": {"defDevSgSn": SN, "userName": "test@example.com"},
    "device/homeDeviceInfo": LIVE,
    "device/getSwitchMode": MODE,
    "device/deviceList": DEVICE_LIST,
    "device/userDeviceInfo": DETAIL,
    "device/getSolarPvPower": PV,
    "device/getDevPowerCutLog": OUTAGES,
    "device/netWorkInfo": NETWORK,
    "device/queryDataElectricityV2": TOTALS,
    "device/queryDataGraphV2": SERIES,
    "device/switchMode": None,
}


def _route_of(url_path: str) -> str:
    for prefix in ("/app-api/", "/api/"):
        if url_path.startswith(prefix):
            return url_path[len(prefix) :]
    return url_path.lstrip("/")


class Recorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.overrides: dict[str, httpx.Response] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = _route_of(request.url.path)
        if path in self.overrides:
            return self.overrides[path]
        if path not in ROUTES:
            return httpx.Response(404, json={"status": 404, "message": "not found"})
        return httpx.Response(200, json={"status": 200, "data": ROUTES[path]})

    def sent(self, path: str) -> httpx.Request:
        for request in reversed(self.requests):
            if request.url.path.endswith(path):
                return request
        raise AssertionError(f"never called {path}")

    def body(self, path: str) -> dict[str, Any]:
        return json.loads(self.sent(path).content)


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
async def client(recorder: Recorder) -> AsyncIterator[EpCubeAsyncClient]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    async with EpCubeAsyncClient(region="EU", token="test-token", http_client=http) as c:
        yield c
    await http.aclose()
