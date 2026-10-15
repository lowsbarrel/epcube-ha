# EP Cube API endpoint inventory

Extracted from the official Android app, `com.eternalplanetenergy.epcube` 2.5.1. The `dynamicPrice/`
routes and the EU probe results below come from the EU build, `com.eternalplanetenergy.epcube.eu` 3.2.0.
Routes are stored Retrofit-style (no leading slash); prefix them with the
regional base URL plus `/`, e.g.
`https://monitoring-eu.epcube.com/api/device/queryDataGraphV2`. `epcube_api/registry.py`
is the record, and `uv run epcube routes` prints it.

**125 routes exist. The Home Assistant integration uses 10.**

Legend: **[HA]** used by the integration · **[✓]** verified working against a
real account · **[?]** present in the app, not yet tested.

---

## The interesting finds

### `device/queryDataGraphV2` **[✓]**: time series, the one that draws the app's graphs

Params: `devId`, `queryDateStr`, `scopeType`.

| scopeType | queryDateStr | returns |
|---|---|---|
| 1 | `YYYY-MM-DD` | **5-minute intervals**, midnight → now (118 points at 09:45) |
| 2 | `YYYY-MM` | one point per day (30) |
| 3 | `YYYY` | one point per month (12) |
| 0 | `YYYY` | one point per year (5) |

Each point is `{"nodeName": "09:45", "scopeType": "1", "nodeVo": {...35 fields}}`.
`nodeName` is the time/date label; `nodeVo` carries the readings.

**`nodeVo` includes `batteryPower` and `batterySoc`**, so battery charge/discharge
power *is* available from the API, per 5-minute interval. The integration derives
it by subtraction instead, which is why it needs `BATTERY_POWER_DEADBAND_KW` to
mask the arithmetic noise. This endpoint gives it directly.

Also per point: grid import/export, solar (AC/DC split), battery charge/discharge
energy, backup and non-backup loads, EV, generator, and the flow-direction fields.

### `dynamicPrice/*` **[✓]**: the saved tariff, and the prices the cube uses in Dynamic mode

Seven routes the 2.5.1 inventory did not have. Checked against a real EU account
(app 3.2.0, the web portal's `/v1/api/` prefix serves the five read routes too).
All are plain bearer-token calls on the usual `/api/` prefix.

| Route | Method | Notes |
|---|---|---|
| `dynamicPrice/getRelation` | GET `devId` | The saved choice: `supportCountryId`/`supportCountryName`, `regionCode`/`regionName`, `productBrand`, `brandId`, `productCode` (import), `productCodeOut` (export), `productName`/`productOutName`, `unitDefault`/`unitSmallest`/`unitMulti` |
| `dynamicPrice/getCountry` | GET `devId` | Countries with Dynamic tariff support; `currentCountry` marks the account's |
| `dynamicPrice/getRegionList` | GET `devId`, `supportCountryId` | Regions of a country (`regionCode`, `regionName`) |
| `dynamicPrice/getBrands` | GET `devId`, `supportCountryId`, `regionCode` | Suppliers in a region |
| `dynamicPrice/getProducts` | GET `devId`, `brandName`, `region`, `productType` | `productType` 0 is import, 1 is export. The app declares `brandId` / `regionCode` for the same call |
| `dynamicPrice/calcuPrice` | GET `devId`, optional `checkTime` | Half-hourly prices: `prices` (import) and `pricesExport`, each `{priceInc, priceExc, startTime, endTime}` in pence, local time. `checkTime` must be a plain `YYYY-MM-DD` (anything else is a 500); a day that is not published yet returns no price lists |
| `dynamicPrice/saveBinding` | POST JSON | Saves the tariff. Body: `devId`, `brandId`, `productBrand`, `supportCountryId`, `productCode`, `productCodeOut`, `regionCode`, `ratio.fraunhofer.{standardImportRatio, importServiceCharge, standardExportRatio, exportServiceCharge}`. `getRelation` follows within about a minute. Returns `data: null` |

What does **not** save the tariff, tested so nobody has to:

- the web portal's `POST /v1/api/home/setDynamicPrice` answers `status: 500`;
- `POST device/switchMode` accepts a `dynamicPriceBinding` block (HTTP 200) and ignores it;
- guessed names (`device/setDynamicPrice`, `device/saveDynamicPrice`, `dynamicPrice/setRelation`, `dynamicPrice/save`, ...) are all 404.

The choices on offer are decided by the vendor, per region. For a UK account the
picker offers Octopus Energy only, with the Agile Octopus versions for import and
Agile Outgoing or the flat Outgoing Octopus for export.

The app's help text says that with no valid price data the system runs in
self-consumption mode (`DynamicPriceBean.noPrice`).

### `device/getSolarPvPower` **[✓]**: per-string PV telemetry

Voltage, current and power for **PV1 to PV4 individually**. Nothing else in the API
exposes this. Useful for spotting a shaded or failing string.

### `device/getDevPowerCutLog` **[✓]**: grid outage history

Every outage with `startTime`, `endTime` and `duration`. The live data only has a
count (`gridPowerFailureNum`); this has the actual events.

### `device/netWorkInfo` **[✓]**: connectivity

`wifiName`, `wifiStatus`, `wifiStatusStr`, `signalLevel`.

### `device/getWarranty` **[✓]**

`activationDate`, `usageEndDate`, `sgSn`, `name`.

---

## device/ (52)

```
assetSave                     getAddressById                queryDataElectricity [500]
bindDevice                    getAssetData                  queryDataElectricityV2  [HA]
checkFirmarkVersion           getDebugConfig                queryDataGraph       [500]
checkSn                       getDevPcsVersion              queryDataGraphV2      [✓]
checkUpgrade                  getDevPowerCutLog     [✓]     refreshData          [405]
checkUpgradeResult            getDeviceBoundUserEmail       replacement/addLog
clearDevInfo                  getEarningsConfig    [404]    replacement/getRMACase
clearTouMode                  getNewDataGraph      [404]    replacement/submitLog
clearTouModeNew               getNewestModeInfo    [404]    saveDebugConfig
debugUpgradeInfo              getRemotePrivilege            saveEarningsConfig
deviceBindAddressInfo         getSettingsData      [404]    saveSettings
deviceBoundUserByInstall      getSolarPvPower       [✓]     scanSgsn
deviceList             [HA]   getSwitchMode        [HA]     submitDebugUpgrade
earningsGraph          [404]  getWarranty           [✓]     submitUpgrade
editDeviceInfo                homeDeviceInfo       [HA]     switchDevice
editDeviceName                homeDeviceInfoWeather [500]   switchMode           [HA]
editRemotePrivilege           netWorkInfo           [✓]     upgrade
                              userDeviceInfo       [HA]
```

`[404]`/`[500]`/`[405]` = tested and rejected as called; most likely need
different parameters or a POST body rather than being absent.

## vpp/ (20): virtual power plant and grid services **[?]**

```
allPrograms          energyhub/event        enrollments        site/program
auth/site            energyhub/events       event              site/programs
commission           energyhub/program      events             userInfo
energyhub/enrollment energyhub/regist       flip/getGlobalSoc
energyhub/userAddress                       flip/updateSoc
enrollment           globalEnrollmentStatus regist
```

`flip/getGlobalSoc` and `flip/updateSoc` suggest remote SoC control by a grid operator.

On the EU server (app 3.2.0) the read-style routes were probed with a plain GET and
every one answers **404**: `allPrograms`, `enrollments`, `events`, `event`,
`globalEnrollmentStatus`, `site/program`, `site/programs`, `energyhub/program`,
`energyhub/events`, `energyhub/enrollment` and `flip/getGlobalSoc`. They are probably
US grid programmes. The write-style routes (`regist`, `commission`, `auth/site`,
`flip/updateSoc`, ...) and `userInfo` / `energyhub/userAddress` were not called.

## open/ (12): unauthenticated

```
common/captcha/check   [HA]   common/getOssDownloadLink   common/uploadImg/avatar
common/captcha/get     [HA]   common/login          [HA]  common/visitorsLogin
common/checkEmailCode         common/register             version/update
common/checkMailCode          common/resetPwd
common/getEmailCode
```

`common/visitorsLogin` is a guest or demo login worth a look.

## user/ (9)

```
user/base  [HA]        user/changePwdByOld    user/queryFirmwareInfo
user/changeEmailByPassword   user/editUserInfo   user/saveUserLanguage
user/changePwdByEmailCode    user/logOff         user/serviceData
```

## smartBreaker/ (5) **[?]**

```
addDevice   deleteDevice   queryDataGraph   saveSettingData   updateDevice
```

Support for a companion smart breaker product, including its own graph endpoint.

## Others

```
message/     changeMsgPushStatus, messageList, messageTypeInfo, readAll
installLog/  queryInstallLogInfo, submit, submitNew, updateInstallLog
help/        helpDetail, helpList
secure/      decrypt, decryptWithPassword
common/      countryCode/list, jpush/registIdAndroid, location/getLocationTree
weatherApi/  weather/getWeather
powerCompany/companyList
dict/        queryDataInfo
afterSale/   submitRepairs
```

---

## Where the list came from

Newer builds add routes, and a route's parameters live in the `ApiService` annotations. Reading them
needs no proxy (no certificate pinning to fight): pull `base.apk` with
`adb shell pm path <package>` / `adb pull` (EU package `com.eternalplanetenergy.epcube.eu`; only
`base.apk` matters), then read the `classes*.dex` string pool for route strings and the
annotation sets for `@GET` / `@POST` / `@Query` names. That is how `dynamicPrice/calcuPrice`
(`devId`, `dynamicChargePrice`, `checkTime`) and `dynamicPrice/saveBinding` (`@Body`) were found.

The app is a native Kotlin app using Retrofit; route strings sit in the `.dex`
string tables in plain UTF-8, so no decompiler is needed. Repository class names
in the same tables (`DeviceRepositoryImpl$queryDataGraphV2$1`) confirm which
routes are actually called and under what method name. `epcube_api/registry.py`
holds the resulting list and its coverage.

A route with no wrapper is still reachable: `client.raw.get(path, **params)` (or
`client.raw.post`) from Python, `uv run epcube probe <path> --param key=value`
from the shell. `epcube_api/registry.py` records every route, whether it has a
wrapper, and what was verified; `uv run epcube routes` prints it.

---

## Known write limitation

`allowChargingXiaGrid` is **read-only** on the hardware this was developed
against (EU cluster, EP Cube HES-EU2-S7-15G, firmware V1.3.0). Four payload
shapes were tried:

| Attempt | Result |
| --- | --- |
| `onlySave=1`, string `"0"` | accepted, ignored |
| `onlySave=0`, string `"0"` | accepted, ignored |
| integer `0` instead of a string | accepted, ignored |
| `allowChargingViaGrid` alongside the misspelled key | accepted, ignored |

Every one returned HTTP 200 with `data: null`, and `getSwitchMode` continued to
report the old value 37 seconds later. `selfConsumptioinReserveSoc` written in
the *same* payload applied immediately, so this is the one field being refused
rather than the write failing.

It may be writable on other firmware, in other regions, or before an installer
locks the grid-connection settings. The integration therefore still offers the
switch, but reads the value back and raises if the device did not take it, and
the battery-override services do not touch the field at all.
