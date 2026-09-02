<div align="center">

# EP Cube

**A Home Assistant integration for EP Cube home batteries, on a client that reaches the whole API.**

The official app talks to an undocumented cloud API. This reads that API properly, including the parts no other integration touches: five-minute history, per-string solar telemetry, and a measured battery power reading.

[![CI](https://github.com/lowsbarrel/epcube-ha/actions/workflows/ci.yml/badge.svg)](https://github.com/lowsbarrel/epcube-ha/actions/workflows/ci.yml)
![Home Assistant](https://img.shields.io/badge/Home_Assistant-41BDF5?logo=homeassistant&logoColor=white)
![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.12+-3776AB?logo=python&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic_2-E92063?logo=pydantic&logoColor=white)
![httpx](https://img.shields.io/badge/httpx-async-2A6DB2)
![Ruff](https://img.shields.io/badge/Ruff-D7FF64?logo=ruff&logoColor=black)
![ty](https://img.shields.io/badge/ty-type_checked-261230)
![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)

[Install](#quickstart) · [What you get](#what-the-integration-gives-you) · [The client](#the-client) · [API reference](docs/api-endpoints.md) · [All docs](#documentation) · [License](#license)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=lowsbarrel&repository=epcube-ha&category=integration)

</div>

---

## What this is

Two things, in one repo.

**A Home Assistant integration.** Config flow, a single coordinator, sensors for every flow and counter, controls for the operating mode and reserve levels, and redacted diagnostics. Cloud polling, one device, no YAML.

**A complete Python client for the API underneath it.** `epcube_api` is async, fully typed, and pydantic-modelled end to end. It is useful on its own, and it has a CLI. The integration is a thin layer over it.

The API surface was recovered by pulling the routes out of the Android app and exercising them against a real system. That turned up **118 routes**, several of which nothing else reaches:

| Route | What it gives you |
| --- | --- |
| `device/queryDataGraphV2` | **Time series.** One reading every five minutes since midnight, carrying `batteryPower` directly instead of leaving it to be inferred |
| `device/getSolarPvPower` | **Per-string PV telemetry.** Voltage, current and power for each MPPT input, so a shaded or failing string is visible |
| `device/getDevPowerCutLog` | **Grid outage history**, with start, end and duration for every event |
| `device/netWorkInfo` | Wi-Fi SSID, signal level, connection state |

## Quickstart

**HACS** (recommended). Click the button above, or add `lowsbarrel/epcube-ha` as a custom repository of type *Integration*. Then **Settings → Devices & Services → Add Integration → EP Cube**.

**Manually.** Copy `custom_components/epcube/` into your `config/custom_components/` and restart.

Setup asks for a region and either a token or your app credentials:

- **Region matters.** An account lives on exactly one cluster (EU, US, JP). A token from the wrong one is rejected as *"token expired"*, which looks identical to a genuinely expired one.
- **Email and password** works when the CAPTCHA solver's dependencies are present; otherwise paste a token, which `uv run epcube login --save` will mint for you.

## What the integration gives you

| Area | Entities |
| --- | --- |
| Live power | Solar, grid, house load, backup load, non-backup load, **battery power** |
| Battery | State of charge, stored energy |
| Solar strings | Voltage, current and power **per MPPT input**, created from whatever the inverter reports |
| Energy | Solar and backup today; grid import/export and battery charge/discharge today; lifetime totals |
| Controls | Operating mode (self-consumption / time-of-use / backup), self-consumption and backup reserve, charge-from-grid |
| Health | Online, fault, alert, grid outage, last outage, last connected, Wi-Fi network, signal level |
| Diagnostics | Redacted download, with the last 25 API calls and which sections were degraded |

Everything is fed by one coordinator, so entity count costs no extra requests.

**Battery power is measured, not guessed.** The live endpoint doesn't report it, so every other integration infers it by subtracting solar and grid from load, arithmetic that carries tens of watts of noise even at rest. The time series reports it directly, and the sensor says which source it used in its `source` attribute.

## The client

```python
import asyncio

from epcube_api import EpCubeAsyncClient, Scope, WorkMode


async def main() -> None:
    async with EpCubeAsyncClient(region="EU", token="…") as client:
        snap = await client.snapshot()
        print(snap.summary_line())

        series = await client.data.series(snap.dev_id, Scope.DAY)
        for when, watts in series.timeline("battery_power_w"):
            print(when, watts)

        config = await client.device.mode(snap.dev_id)
        await client.device.set_mode(config, WorkMode.BACKUP)


asyncio.run(main())
```

There is a CLI too:

```sh
uv sync --extra login
cp .env.example .env          # region + credentials
uv run epcube login --save
uv run epcube status
```

```
EP Cube 4953  (EU)
  SoC 93%  solar 384W  grid 0W  load 22W  battery +362W  Self-consumption

  battery power                  +362 W  (measured)
  pv string 1                    185.8 V  7.9 A  1460 W
  pv string 2                    283.0 V  8.5 A  2430 W
  outages logged                 1
```

Also: `epcube series` (curves at any scope), `epcube pv`, `epcube routes` (the whole surface and its coverage), `epcube probe <path>` for a route with no wrapper yet.

### The one trap worth knowing

`device/switchMode` treats a field that is **absent** from the payload as *reset this to default*. Send `{"devId": …, "workStatus": "3"}` to switch to backup mode and the device also loses its entire tariff calendar and both reserve levels.

So a write is a model, never a dict. It declares every field the endpoint understands and serialises with `exclude_none=False`, which makes a partial payload unrepresentable:

```python
config = await client.device.mode(dev_id)
request = SwitchModeRequest.from_config(config).with_changes(self_consumption_reserve_soc="25")
await client.device.switch_mode(request)
```

## Stack

| Layer | Choice |
| --- | --- |
| HTTP | `httpx`, async, with retry and both of the API's error layers handled |
| Models | pydantic v2, with camelCase aliases and coercions for the API's string-typed numbers |
| Integration | Coordinator + `runtime_data`, config flow with reauth, entity translations |
| Lint & format | Ruff |
| Types | ty |
| Tests | pytest over `httpx.MockTransport`, so no network and no credentials. 100% statement and branch coverage, enforced |
| CI | Conventional Commits, secret scan, the verification bar, hassfest, HACS validation |
| Packaging | uv, with a lockfile CI installs frozen |

## Layout

| Path | What's in it |
| --- | --- |
| `custom_components/epcube/` | The Home Assistant integration |
| `epcube_api/` | The client: `models/`, `endpoints/`, `transport.py`, `cli.py` |
| `epcube_api/registry.py` | Every discovered route, and whether it has a wrapper |
| `docs/api-endpoints.md` | The prose inventory, and what's verified against real hardware |
| `tools/extract_apk_endpoints.py` | How the route list was recovered from the APK |
| `tests/` | Offline suite |

## Development

```sh
uv sync --all-extras
sh scripts/verify.sh     # the "done" bar: secret scan + ruff + ty + pytest
```

The pre-commit hook and CI run exactly that, so a green local run predicts a green PR. Work happens on short-lived branches off `main` and lands through squash-merged pull requests. There is no staging branch and no release branch.

## Documentation

| Doc | What's inside |
| --- | --- |
| [setup.md](docs/setup.md) | Installing the integration, and setting up for development |
| [architecture.md](docs/architecture.md) | How the client and the integration fit together, and why the client is async-only |
| [api-endpoints.md](docs/api-endpoints.md) | All 118 routes, what's verified, and how to explore the rest |
| [testing.md](docs/testing.md) | The offline suite, and how to test against real hardware |
| [deploy.md](docs/deploy.md) | Releases, HACS distribution, CI and repo policy |

**The one rule:** a write to `switchMode` is always a complete payload built from a fresh read. Everything else follows from [AGENTS.md](AGENTS.md).

## Requirements

Home Assistant 2025.2+ · Python 3.13+ · an EP Cube account.

## License

[MIT](LICENSE). Use it, fork it, ship it. If you extend the API coverage, contributing it back saves the next person another APK teardown.

Unofficial, and unaffiliated with EP Cube, Canadian Solar or CSI Solar. The API is undocumented and may change without notice.
