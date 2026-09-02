# Architecture

Two layers with a hard line between them: a standalone client that knows the EP
Cube API, and a Home Assistant integration that knows nothing else.

```
.
├── epcube_api/                the client - usable without Home Assistant
│   ├── const.py               regions, enums, timeouts, the app user agent
│   ├── transport.py           httpx, retries, both of the API's error layers
│   ├── exceptions.py          the error hierarchy
│   ├── auth.py                the login CAPTCHA solver
│   ├── registry.py            every discovered route + its coverage
│   ├── cli.py                 the `epcube` command
│   ├── models/                pydantic request and response shapes
│   └── endpoints/             one module per area of the API
├── custom_components/epcube/  the Home Assistant integration
├── scripts/                   verify.sh (the 'done' bar) + release bundling
├── tests/                     offline suite over httpx.MockTransport
└── tools/                     how the route list was recovered from the APK
```

## Why the client is async-only

An earlier draft had one set of endpoint definitions serving both a sync and an
async client, by returning "the value, or an awaitable of it". It worked at
runtime and was unverifiable at type-check time: no single signature is honestly
typed as both awaitable and not, so `ty` rejected every call site on one side or
the other.

Both real consumers — Home Assistant and the CLI — are happy in an event loop, so
the surface is async and fully typed rather than dual-mode and unchecked. A sync
facade could be added later; it would be mechanical.

## The shape of a call

```
client.device.mode(dev_id)
  → DeviceEndpoints._get("device/getSwitchMode", parse_model(ModeConfig), devId=…)
    → AsyncTransport.request(Request(...))
        builds the URL from Region, adds the auth header
        retries 429 / 5xx / timeouts with backoff
        maps HTTP status *and* the body's `status` field to exceptions
    → ModeConfig.model_validate(payload)
```

Three things are load-bearing there:

**Errors live in two places.** The EU cluster uses HTTP status codes; US and JP
answer HTTP 200 and put the real code in the body's `status`. `_process` checks
both, so an expired token raises on every cluster instead of looking like an
empty success on two of them.

**Field names are verified, not guessed.** The API's casing is not
self-consistent — `backUpPower` but `backupLoadsMode`, `defTimeZone` but `devId`,
`off_ON_Grid_Hint`, and the misspelled `selfConsumptioinReserveSoc`. A wrong
alias fails silently as `None`, so models are diffed against real payloads.

**Unknown fields are kept.** `EpCubeModel` sets `extra="allow"`, so a firmware
update adds data to `.extras` rather than losing it.

## The write path

`device/switchMode` treats a field that is *absent* from the payload as "reset
this to default". A partial body wipes the tariff calendar and both reserve
levels.

So the payload is a model, not a dict. `SwitchModeRequest` declares every field
the endpoint understands, serialises with `exclude_none=False`, and is built by
`from_config()` from a fresh `ModeConfig` read. Changing one setting is
`.with_changes(...)`, which carries the rest through untouched. A partial payload
is not expressible.

## The integration

One coordinator, one device, one refresh per interval:

```
EpCubeCoordinator._async_update_data
  → client.snapshot()          gathers every read concurrently
  → Snapshot                   live + mode + detail + pv + network + totals
  → entities read from it      no entity issues its own request
```

`Snapshot` treats only the live read as mandatory. A supplementary read that
fails records into `Snapshot.errors`, and entities bound to that section go
unavailable rather than reporting a stale value as current
(`EpCubeSectionEntity`).

Two values have several possible sources of differing quality, and the entity
exposes which one it used in a `source` attribute:

| Value | Preferred | Fallback | Why |
| --- | --- | --- | --- |
| Battery power | the series, which reports it directly | derived from solar + grid − load | the derived value carries sampling noise; the live endpoint has no battery power field at all |
| Solar power | the series, then the per-string endpoint | `live.solar_power` | on a live system `live.solar_power` read 49 W while the strings read 1052 W and the series read 1.05 kW for the same fresh timestamp — the latter two agree exactly |

### Sign convention

The API sends `batteryPower` **negative when charging**. This was established
from the energy balance, which only closes with that sign:

```
solar + grid − load + battery == 0
1.05  +  0.0 − 0.11 + (−0.94) == 0.00     while the state of charge climbed
```

Everything exposed by this package uses the opposite, more conventional
direction — **positive = charging** — so `SeriesReading.battery_power_w` negates
the raw field and `LiveSnapshot.battery_power` (a derivation) already matches.
Only `SeriesReading.battery_power` carries the raw value.

## Where the route list came from

The app stores its Retrofit routes as plain strings in the APK's dex string
tables, so `tools/extract_apk_endpoints.py` reads all 118 of them without a
decompiler. `registry.py` records each one and whether it has a wrapper;
[api-endpoints.md](api-endpoints.md) is the prose version.
