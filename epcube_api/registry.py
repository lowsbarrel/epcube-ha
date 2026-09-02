"""Every route found in the Android app, whether or not it has a wrapper yet.

Extracted from `com.eternalplanetenergy.epcube` with
`tools/extract_apk_endpoints.py`: routes are stored Retrofit-style in the dex
string tables, so the complete list is readable without a decompiler.

This is the inventory, not the implementation. A route with `wrapper=None` has no
typed method because no response has ever been observed from it - reach it with
`client.raw.get(route.path, ...)`, and once you know its shape, model it and fill
in the wrapper. `docs/api-endpoints.md` is the prose version.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Verified(StrEnum):
    """How much is actually known about a route."""

    WORKING = "working"
    """Called successfully against a real account; the response shape is known."""
    REJECTED = "rejected"
    """Exists but refused the parameters tried - a 500 or 405, not a 404."""
    ABSENT = "absent"
    """Returned 404 on the EU cluster. May exist elsewhere, or need a POST."""
    UNTESTED = "untested"
    """Present in the app, never called from here."""


@dataclass(frozen=True, slots=True)
class Route:
    path: str
    group: str
    verified: Verified = Verified.UNTESTED
    wrapper: str | None = None
    """Dotted client path, e.g. `device.home_info`, or None if unwrapped."""
    note: str = ""

    @property
    def wrapped(self) -> bool:
        return self.wrapper is not None


def _r(
    path: str,
    verified: Verified = Verified.UNTESTED,
    wrapper: str | None = None,
    note: str = "",
) -> Route:
    return Route(path, path.split("/")[0], verified, wrapper, note)


W, R, A, U = Verified.WORKING, Verified.REJECTED, Verified.ABSENT, Verified.UNTESTED

ROUTES: tuple[Route, ...] = (
    # --- device: verified ---
    _r("device/homeDeviceInfo", W, "device.home_info", "live snapshot; the only source of devId"),
    _r("device/deviceList", W, "device.all", "richest metadata on the account"),
    _r("device/userDeviceInfo", W, "device.detail"),
    _r("device/getSwitchMode", W, "device.mode", "read side of switchMode"),
    _r("device/switchMode", W, "device.switch_mode", "omitted fields are RESET"),
    _r("device/queryDataElectricityV2", W, "data.totals"),
    _r("device/queryDataGraphV2", W, "data.series", "time series; 5-minute resolution at DAY"),
    _r("device/getSolarPvPower", W, "device.pv_strings", "per-MPPT-string telemetry"),
    _r("device/getDevPowerCutLog", W, "device.outages"),
    _r("device/netWorkInfo", W, "device.network"),
    _r("device/getWarranty", W, "device.warranty"),
    # --- device: exists, parameters unknown ---
    _r("device/queryDataElectricity", R, None, "v1; 500s on every parameter set tried"),
    _r("device/queryDataGraph", R, None, "v1 of the series route"),
    _r("device/refreshData", R, None, "405 on GET - needs POST"),
    _r("device/homeDeviceInfoWeather", R, None, "500: wants a serial this account lacks"),
    # --- device: 404 as called ---
    _r("device/getNewDataGraph", A),
    _r("device/earningsGraph", A),
    _r("device/queryPriceDataGraphV2", A, "data.price_series", "needs dynamic pricing enabled"),
    _r("device/getSettingsData", A),
    _r("device/getNewestModeInfo", A),
    # --- device: untested ---
    _r("device/getDevPcsVersion", U, "device.firmware_version"),
    _r("device/checkUpgrade", U, "device.check_upgrade"),
    _r("device/getEarningsConfig", U, "data.earnings"),
    *(
        _r(f"device/{name}")
        for name in (
            "assetSave",
            "bindDevice",
            "checkFirmarkVersion",
            "checkSn",
            "checkUpgradeResult",
            "clearDevInfo",
            "clearTouMode",
            "clearTouModeNew",
            "debugUpgradeInfo",
            "deviceBindAddressInfo",
            "deviceBoundUserByInstall",
            "editDeviceInfo",
            "editDeviceName",
            "editRemotePrivilege",
            "getAddressById",
            "getAssetData",
            "getDebugConfig",
            "getDeviceBoundUserEmail",
            "getRemotePrivilege",
            "replacement/addLog",
            "replacement/getRMACase",
            "replacement/submitLog",
            "saveDebugConfig",
            "saveEarningsConfig",
            "saveSettings",
            "scanSgsn",
            "submitDebugUpgrade",
            "submitUpgrade",
            "switchDevice",
            "upgrade",
        )
    ),
    # --- user ---
    _r("user/user/base", W, "account.base", "defDevSgSn is the plant serial"),
    _r("user/user/queryFirmwareInfo", U, "account.firmware_info"),
    _r("user/user/serviceData", U, "account.service_data"),
    _r("user/user/saveUserLanguage", U, "account.set_language"),
    _r("user/user/editUserInfo", U, "account.edit_profile"),
    _r("user/user/changePwdByOld", U, "account.change_password"),
    *(
        _r(f"user/user/{name}")
        for name in ("changeEmailByPassword", "changePwdByEmailCode", "logOff")
    ),
    # --- open (unauthenticated) ---
    _r("open/common/captcha/get", W, "public.captcha"),
    _r("open/common/captcha/check", W, "public.verify_captcha"),
    _r("open/common/login", W, "public.login"),
    _r("open/common/getEmailCode", U, "public.request_email_code"),
    _r("open/version/update", U, "public.app_version"),
    *(
        _r(f"open/common/{name}")
        for name in (
            "checkEmailCode",
            "checkMailCode",
            "getOssDownloadLink",
            "register",
            "resetPwd",
            "uploadImg/avatar",
            "visitorsLogin",
        )
    ),
    # --- vpp: virtual power plant, entirely untested ---
    _r("vpp/userInfo", U, "vpp.user_info"),
    _r("vpp/allPrograms", U, "vpp.programs"),
    _r("vpp/site/programs", U, "vpp.site_programs"),
    _r("vpp/enrollments", U, "vpp.enrollments"),
    _r("vpp/globalEnrollmentStatus", U, "vpp.enrollment_status"),
    _r("vpp/events", U, "vpp.events"),
    _r("vpp/flip/getGlobalSoc", U, "vpp.global_soc", "operator-set SoC target"),
    *(
        _r(f"vpp/{name}")
        for name in (
            "auth/site",
            "commission",
            "energyhub/enrollment",
            "energyhub/event",
            "energyhub/events",
            "energyhub/program",
            "energyhub/regist",
            "energyhub/userAddress",
            "enrollment",
            "event",
            "flip/updateSoc",
            "regist",
            "site/program",
        )
    ),
    # --- smart breaker ---
    _r("smartBreaker/queryDataGraph", U, "breaker.graph", "per-circuit history"),
    _r("smartBreaker/addDevice", U, "breaker.add"),
    _r("smartBreaker/updateDevice", U, "breaker.update"),
    _r("smartBreaker/saveSettingData", U, "breaker.save_settings"),
    _r("smartBreaker/deleteDevice", U),
    # --- messaging and support ---
    _r("message/messageList", U, "messages.list"),
    _r("message/messageTypeInfo", U, "messages.types"),
    _r("message/readAll", U, "messages.read_all"),
    _r("message/changeMsgPushStatus", U, "messages.set_push"),
    _r("help/helpList", U, "support.help_list"),
    _r("help/helpDetail", U, "support.help_detail"),
    _r("installLog/queryInstallLogInfo", U, "support.install_log"),
    _r("weatherApi/weather/getWeather", U, "support.weather"),
    *(
        _r(name)
        for name in (
            "installLog/submit",
            "installLog/submitNew",
            "installLog/updateInstallLog",
            "afterSale/submitRepairs",
            "common/countryCode/list",
            "common/jpush/registIdAndroid",
            "common/location/getLocationTree",
            "dict/queryDataInfo",
            "powerCompany/companyList",
            "secure/decrypt",
            "secure/decryptWithPassword",
        )
    ),
)


def by_group() -> dict[str, list[Route]]:
    groups: dict[str, list[Route]] = {}
    for route in ROUTES:
        groups.setdefault(route.group, []).append(route)
    return groups


def find(path: str) -> Route | None:
    return next((r for r in ROUTES if r.path == path), None)


def coverage() -> dict[str, int]:
    """How much of the discovered surface has a typed wrapper."""
    return {
        "total": len(ROUTES),
        "wrapped": sum(1 for r in ROUTES if r.wrapped),
        "verified": sum(1 for r in ROUTES if r.verified is Verified.WORKING),
    }
