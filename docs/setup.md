# Setup

## Installing the integration

### HACS

The repository ships releases only. HACS never offers the default branch
(`hide_default_branch` in `hacs.json`), so you always get a tagged, verified
build.

1. HACS → ⋮ → **Custom repositories** → add `lowsbarrel/epcube-ha`, category
   **Integration**. (Or use the button in the [README](../README.md).)
2. Install, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → EP Cube**.

The release bundle carries the API client inside it, so the only thing Home
Assistant installs from PyPI is `pydantic`.

### Manually

Download `epcube.zip` from a
[release](https://github.com/lowsbarrel/epcube-ha/releases) and unpack it into
`config/custom_components/`, so you end up with `config/custom_components/epcube/`.
Restart.

Copying the repository folder directly will *not* work: `custom_components/epcube/`
in the source tree imports `epcube_api`, which the release bundles but the source
tree keeps separate. Either use a release, or `pip install -e .` into Home
Assistant's environment.

## Configuring it

You need two things: the **region** and a **token**.

**Region is not cosmetic.** An account exists on exactly one cluster: EU, US or
JP. A token minted against the wrong one is rejected as *"User token expired"*,
identical to a genuinely expired token. If setup fails with an auth error and you
are sure of the credentials, try another region before anything else.

**Token.** The config flow offers two paths:

- *Sign in with email and password*, available only when the CAPTCHA solver's
  dependencies are importable. The login endpoint is guarded by a slide puzzle,
  which is solved locally and occasionally needs a second attempt.
- *Paste an access token*, always available. Mint one with the CLI below, or
  from any tool that produces an EP Cube Bearer token.

Tokens expire. When one does, the integration raises a reauth flow and Home
Assistant prompts for a replacement; nothing else needs reconfiguring.

### Options

| Option | Default | What it costs |
| --- | --- | --- |
| Update interval | 60 s | the live tier — live, mode, PV (3 reads) — every cycle; keeps power/SoC responsive |
| History interval | 30 min | the slow reads — device details, outages, totals, five-minute series — on their own loop |
| Read the five-minute history | on | one request per history interval; the only source of a *measured* battery power reading |
| Read monthly/yearly/lifetime totals | off | four requests per history interval, for counters that barely move; turn on to feed the Energy dashboard from the lifetime sensors |

### Energy dashboard

The integration exposes ordinary `total_increasing` energy sensors, so the Energy
dashboard reads them the standard way - and, unlike an external statistic, they
accept a **fixed price** in the dashboard, so cost tracking works with no extra
setup. Open **Settings → Dashboards → Energy** and set the sources to:

| Dashboard source | Sensor | Notes |
| --- | --- | --- |
| Solar production | **Solar today** | from the live read, always available |
| Grid consumption | **Grid import today** | from the live read |
| Return to grid | **Grid export today** | from the live read |
| Battery in | **Battery charged** | derived, forward-only (see below) |
| Battery out | **Battery discharged** | derived, forward-only (see below) |

Prefer the monotonic lifetime counters (**Solar total**, **Grid import total**,
**Grid export total**) instead? Turn on **Read monthly/yearly/lifetime totals**
so they hold a value, then point the sources at them.

**No pre-install history.** HA builds statistics from what it records live, so
days before you installed the integration stay blank; there is no backfill. The
EP Cube API resolves past days only at daily granularity, so a backfill would be
flat daily bars anyway - not worth the external-statistics machinery and the
fixed-price restriction it drags in.

The API does not report battery in/out *energy* - those counters read zero at
every scope - so the **Battery charged** and **Battery discharged** sensors
derive it by tracking the stored-energy level each refresh (see `battery.py`).
This is a best-effort figure whose accuracy improves with a shorter update
interval.

## Development

```sh
uv sync --all-extras     # client, CAPTCHA solver, Home Assistant, tooling
cp .env.example .env     # fill in region + credentials
uv run epcube login --save
uv run epcube status
```

Then wire the commit gate once:

```sh
git config core.hooksPath .githooks
```

`sh scripts/verify.sh` is the whole bar: secret scan, ruff, ty, pytest. The hook
and CI run exactly that script, so a green local run predicts a green PR. See
[testing.md](testing.md).

Home Assistant is a dev dependency purely so `ty` can check the integration
against real HA types. It is not needed to use the client.

## Credentials

`.env` is gitignored; `.env.example` lists every variable the code reads. Nothing
reads credentials from anywhere else, and `scripts/check-secrets.sh` blocks the
obvious slips in the hook and in CI.

Be aware that the API returns the owner's name, postal address, GPS coordinates
and email on several endpoints. `epcube status --json` and a raw `probe` will
show all of it. The integration's diagnostics download redacts it, but a
hand-made dump does not.
