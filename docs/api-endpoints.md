# EP Cube API endpoint inventory

Extracted from the official Android app, `com.eternalplanetenergy.epcube` 2.5.1,
with `tools/extract_apk_endpoints.py`. Routes are stored Retrofit-style (no
leading slash) in the dex string tables; prefix them with the regional base URL
plus `/`, e.g. `https://monitoring-eu.epcube.com/api/device/queryDataGraphV2`.

**145 routes exist. The Home Assistant integration uses 10.**

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
clearDevInfo                  getEarningsConfig             replacement/getRMACase
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

Entirely unexplored. `flip/getGlobalSoc` and `flip/updateSoc` suggest remote SoC
control by a grid operator.

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

## Reproducing this

```
uv run tools/extract_apk_endpoints.py <path-to-apk-or-xapk>
```

The app is a native Kotlin app using Retrofit; route strings sit in the `.dex`
string tables in plain UTF-8, so no decompiler is needed. Repository class names
in the same tables (`DeviceRepositoryImpl$queryDataGraphV2$1`) confirm which
routes are actually called and under what method name.

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
