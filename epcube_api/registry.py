from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Verified(StrEnum):
    WORKING = "working"
    REJECTED = "rejected"
    ABSENT = "absent"
    UNTESTED = "untested"


@dataclass(frozen=True, slots=True)
class Route:
    path: str
    group: str
    verified: Verified = Verified.UNTESTED
    wrapper: str | None = None
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
    _r("device/queryDataElectricity", R, None, "v1; 500s on every parameter set tried"),
    _r("device/queryDataGraph", R, None, "v1 of the series route"),
    _r("device/refreshData", R, None, "405 on GET - needs POST"),
    _r("device/homeDeviceInfoWeather", R, None, "500: wants a serial this account lacks"),
    _r("device/getNewDataGraph", A),
    _r("device/earningsGraph", A),
    _r("device/queryPriceDataGraphV2", A, "data.price_series", "needs dynamic pricing enabled"),
    _r("device/getSettingsData", A),
    _r("device/getNewestModeInfo", A),
    _r("device/getDevPcsVersion", U, "device.firmware_version"),
    _r("device/checkUpgrade", U, "device.check_upgrade"),
    _r("device/getEarningsConfig", A, "data.earnings", "404 on the EU server (app 3.2.0)"),
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
    _r(
        "dynamicPrice/getRelation",
        W,
        None,
        "the saved country / region / supplier / import + export product (EU, app 3.2.0)",
    ),
    _r("dynamicPrice/getCountry", W, None, "countries with Dynamic tariff support"),
    _r("dynamicPrice/getRegionList", W, None, "param: supportCountryId"),
    _r("dynamicPrice/getBrands", W, None, "params: supportCountryId, regionCode"),
    _r(
        "dynamicPrice/getProducts",
        W,
        None,
        "params: brandId or brandName, regionCode or region, productType (0 import, 1 export)",
    ),
    _r(
        "dynamicPrice/calcuPrice",
        W,
        None,
        "GET devId[, checkTime=YYYY-MM-DD]: half-hourly import (prices) and export "
        "(pricesExport), priceInc/priceExc (with/without VAT) in the tariff currency, local time",
    ),
    _r(
        "dynamicPrice/saveBinding",
        W,
        None,
        "POST JSON: devId, brandId, productBrand, supportCountryId, productCode, productCodeOut, "
        "regionCode, ratio.fraunhofer.*; changes the saved tariff",
    ),
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
    _r("vpp/userInfo", U, "vpp.user_info"),
    _r("vpp/allPrograms", A, "vpp.programs", "404 on the EU server (app 3.2.0)"),
    _r("vpp/site/programs", A, "vpp.site_programs", "404 on the EU server (app 3.2.0)"),
    _r("vpp/enrollments", A, "vpp.enrollments", "404 on the EU server (app 3.2.0)"),
    _r("vpp/globalEnrollmentStatus", A, "vpp.enrollment_status", "404 on the EU server"),
    _r("vpp/events", A, "vpp.events", "404 on the EU server (app 3.2.0)"),
    _r("vpp/flip/getGlobalSoc", A, "vpp.global_soc", "operator-set SoC target; 404 on EU"),
    *(
        _r(f"vpp/{name}")
        for name in (
            "auth/site",
            "commission",
            "energyhub/event",
            "energyhub/regist",
            "energyhub/userAddress",
            "enrollment",
            "flip/updateSoc",
            "regist",
        )
    ),
    _r("vpp/energyhub/enrollment", A, None, "404 on the EU server (app 3.2.0)"),
    _r("vpp/energyhub/events", A, None, "404 on the EU server (app 3.2.0)"),
    _r("vpp/energyhub/program", A, None, "404 on the EU server (app 3.2.0)"),
    _r("vpp/event", A, None, "404 on the EU server (app 3.2.0)"),
    _r("vpp/site/program", A, None, "404 on the EU server (app 3.2.0)"),
    _r("smartBreaker/queryDataGraph", U, "breaker.graph", "per-circuit history"),
    _r("smartBreaker/addDevice", U, "breaker.add"),
    _r("smartBreaker/updateDevice", U, "breaker.update"),
    _r("smartBreaker/saveSettingData", U, "breaker.save_settings"),
    _r("smartBreaker/deleteDevice", U),
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


def coverage() -> dict[str, int]:
    return {
        "total": len(ROUTES),
        "wrapped": sum(1 for r in ROUTES if r.wrapped),
        "verified": sum(1 for r in ROUTES if r.verified is Verified.WORKING),
    }
