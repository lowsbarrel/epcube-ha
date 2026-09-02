# Testing

## The verification bar

"Done" has one definition: everything [`scripts/verify.sh`](../scripts/verify.sh)
runs. The pre-commit hook and CI both call that script, so it cannot mean two
different things.

```sh
sh scripts/verify.sh
```

| Step | Tool | Catches |
| --- | --- | --- |
| `check-secrets` | zero-dependency scan | credentials about to be committed |
| `lint` | `ruff check` + `ruff format --check` | style, import order, common bugs |
| `types` | `ty` | wrong types, bad overrides, misuse of the Home Assistant API |
| `test` | `pytest` | behaviour |

CI adds two checks the Python toolchain cannot do: **hassfest** (manifest and
translation validity) and **HACS validation** (that the repository is
installable).

## The offline suite

`tests/` runs the real client against `httpx.MockTransport`. No network, no
credentials, no recorded cassettes to rot — the fixtures are written by hand from
observed payloads.

They deliberately preserve the API's quirks:

- numbers as strings (`"0.70"`, `"15.0kWh"`)
- the misspelled `selfConsumptioinReserveSoc`, whose correctly-spelled twin the
  server silently ignores
- `workParam` as a JSON _string_ rather than an object
- `hasValue` reading `0` on every point of a real series, populated or not
- the real casing: `backUpPower`, `defTimeZone`

**A fixture that tidies those up stops protecting anything.** Several of them
encode bugs that were live before the fixture existed.

Beyond parsing, the suite covers:

- **The write trap.** That a mode change still sends the tariff calendar and both
  reserve levels, that `activeWeek` is coerced to strings, and that even an empty
  config produces a complete payload.
- **Both error layers.** HTTP 401, and HTTP 200 carrying `status: 401` the way the
  US and JP clusters report it.
- **Degradation.** That a failing statistics endpoint leaves the live data intact
  and records into `Snapshot.errors`.
- **Sign and source conventions.** That battery power comes out positive when
  charging, and that solar prefers the sources which agree with each other.

## Against real hardware

The CLI is the fastest way to see whether a change survives contact with a real
system:

```sh
uv run epcube status                  # one screen
uv run epcube status --json           # everything, for diffing
uv run epcube series --scope month --field solar_electricity
uv run epcube probe device/getAssetData --param devId=1234
```

`epcube probe` is for routes with no wrapper yet — see
[api-endpoints.md](api-endpoints.md). A 404 means the route does not exist; a 500
usually means it does exist and the parameters are wrong.

## The integration, in a real Home Assistant

The offline suite and the type checker both pass on code that is still wrong
about the device. Two bugs were found only by running the integration against a
live system: the battery-power **sign** was inverted, and `live.solar_power`
turned out not to be total PV production at all.

```sh
uv build --wheel
# an image of the stock HA plus the wheel installed
docker build -t epcube-ha-test -f Dockerfile.test .
docker run -d --name epcube-ha -v "$PWD/ha-config:/config" -p 8123:8123 epcube-ha-test
docker logs -f epcube-ha | grep -i epcube
```

Add the integration at <http://localhost:8123>, then check the entity states.
Look for `unknown` or `unavailable`: against a healthy system every entity should
carry a value, and the coordinator should log `success: True` on each interval.

Cross-check anything suspicious against `epcube status` and the raw payload —
that is how both of the above were caught.

## Writing tests

- A bug fix comes with a test that fails before it and passes after.
- Prefer a fixture that reproduces the real payload over one that is convenient.
- Keep tests isolated: no shared mutable state, clean up what you create.
- The mechanical checks catch slips only; they are not a substitute for review.
