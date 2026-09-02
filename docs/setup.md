# Setup

## Installing the integration

### HACS

The repository ships releases only — HACS never offers the default branch
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

**Region is not cosmetic.** An account exists on exactly one cluster — EU, US or
JP. A token minted against the wrong one is rejected as *"User token expired"*,
identical to a genuinely expired token. If setup fails with an auth error and you
are sure of the credentials, try another region before anything else.

**Token.** The config flow offers two paths:

- *Sign in with email and password* — available only when the CAPTCHA solver's
  dependencies are importable. The login endpoint is guarded by a slide puzzle,
  which is solved locally and occasionally needs a second attempt.
- *Paste an access token* — always available. Mint one with the CLI below, or
  from any tool that produces an EP Cube Bearer token.

Tokens expire. When one does, the integration raises a reauth flow and Home
Assistant prompts for a replacement; nothing else needs reconfiguring.

### Options

| Option | Default | What it costs |
| --- | --- | --- |
| Update interval | 30 s | one live read plus the enabled extras |
| Read the five-minute history | on | one extra request; the only source of a *measured* battery power reading |
| Read monthly/yearly/lifetime totals | off | four extra requests per update, for counters that barely move |

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

`sh scripts/verify.sh` is the whole bar — secret scan, ruff, ty, pytest. The hook
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
show all of it — the integration's diagnostics download redacts it, but a
hand-made dump does not.
