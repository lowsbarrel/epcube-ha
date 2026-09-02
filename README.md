<div align="center">

# EP Cube

**Home Assistant integration and Python client for EP Cube home battery systems**

[![CI](https://github.com/lowsbarrel/epcube-ha/actions/workflows/ci.yml/badge.svg)](https://github.com/lowsbarrel/epcube-ha/actions/workflows/ci.yml)

[Setup](docs/setup.md) · [API reference](docs/api-endpoints.md) · [Architecture](docs/architecture.md) · [Conventions](AGENTS.md)

</div>

---

A complete, typed client for the EP Cube cloud API — the undocumented one the
official iOS and Android apps talk to — plus the Home Assistant integration built
on top of it.

The API surface was recovered by reading the routes out of the Android app and
exercising them against a real system. That turned up **118 routes**, including
several nothing else reaches:

| Route | What it gives you |
| --- | --- |
| `device/queryDataGraphV2` | **Time series** — a reading every five minutes since midnight, with `batteryPower` reported directly rather than inferred from the other flows |
| `device/getSolarPvPower` | **Per-string PV telemetry** — voltage, current and power for each MPPT input, so a shaded or failing string is visible |
| `device/getDevPowerCutLog` | **Grid outage history**, with timestamps and durations |
| `device/netWorkInfo` | Wi-Fi SSID, signal level, connection state |

[`docs/api-endpoints.md`](docs/api-endpoints.md) is the full inventory;
`epcube_api/registry.py` is the machine-readable version, and `epcube routes`
shows how much of it has a typed wrapper.

## Quickstart

```sh
uv sync                       # client only
uv sync --extra login         # adds the CAPTCHA solver needed to mint a token

cp .env.example .env          # then fill in EPCUBE_REGION and your credentials
uv run epcube login --save    # mints a Bearer token into .env
uv run epcube status
```

```
EP Cube 4953  (EU)
  SoC 93%  solar 384W  grid 0W  load 22W  battery +362W  Self-consumption

  battery                        93%  (13.96 kWh)
  battery power                  +362 W  (measured)
  pv string 1                    185.8 V  7.9 A  1460 W
  pv string 2                    283.0 V  8.5 A  2430 W
  outages logged                 1
                                 2026-09-01 12:19 → 2026-09-01 12:26 (7m)
```

Other commands: `epcube series` (curves, any scope), `epcube pv`,
`epcube routes`, and `epcube probe <path>` for a route with no wrapper yet.

## The library

Async, typed, pydantic models throughout.

```python
import asyncio
from epcube_api import EpCubeAsyncClient, Scope, WorkMode


async def main() -> None:
    async with EpCubeAsyncClient(region="EU", token="…") as client:
        snap = await client.snapshot()
        print(snap.battery_soc, snap.battery_power_w)

        series = await client.data.series(snap.dev_id, Scope.DAY)
        for when, watts in series.timeline("battery_power_w"):
            print(when, watts)

        config = await client.device.mode(snap.dev_id)
        await client.device.set_mode(config, WorkMode.BACKUP)


asyncio.run(main())
```

### The one trap worth knowing

`device/switchMode` treats a field that is **absent** from the payload as *reset
this to default*. Send `{"devId": …, "workStatus": "3"}` to switch to backup mode
and the device also loses its entire tariff calendar and both reserve levels.

So writes take a `SwitchModeRequest` built from a fresh read, never a dict:

```python
config = await client.device.mode(dev_id)
request = SwitchModeRequest.from_config(config).with_changes(self_consumption_reserve_soc="25")
await client.device.switch_mode(request)
```

The model declares every field the endpoint understands and serialises with
`exclude_none=False`, so a partial payload is not expressible.

## Layout

| Path | What's in it |
| --- | --- |
| `epcube_api/` | The client — `models/`, `endpoints/`, `transport.py`, `cli.py` |
| `custom_components/epcube/` | The Home Assistant integration |
| `docs/api-endpoints.md` | Every route found in the app, and what's verified |
| `tools/extract_apk_endpoints.py` | How the route list was recovered |
| `tests/` | Offline suite, over `httpx.MockTransport` |

## Development

```sh
sh scripts/verify.sh          # secret scan + ruff + ty + pytest — the "done" bar
```

The pre-commit hook and CI run exactly this, so a green local run predicts a
green PR. Conventions live in [`AGENTS.md`](AGENTS.md).

## Status

The client works and is verified against a live EU system: 15 routes confirmed,
45 with typed wrappers, and every response model diffed field-by-field against
real payloads. **The Home Assistant integration is not written yet.**

Unofficial, and unaffiliated with EP Cube, Canadian Solar or CSI Solar. The API
is undocumented and may change without notice.
