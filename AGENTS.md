# EP Cube

A Home Assistant integration for EP Cube home batteries, on an async client that
reaches the whole undocumented cloud API. Two halves:

| Half        | Where                       | Owns                                                                    |
| ----------- | --------------------------- | ----------------------------------------------------------------------- |
| Client      | `epcube_api/`               | httpx transport, pydantic models, endpoint wrappers, CLI, CAPTCHA login |
| Integration | `custom_components/epcube/` | Config flow, one coordinator, entities, services, diagnostics           |

All commands run from the repo root. uv is the package manager; Python is 3.14,
the version Home Assistant runs.

# The shape

Every read is **entity → coordinator → `client.snapshot()` → endpoint wrapper →
`AsyncTransport` → pydantic model**. No entity issues its own request: the
coordinator owns one `Snapshot` per cycle and entities read from it. An endpoint
wrapper is thin: build the `Request`, call the transport, parse into a model.
Retries and error mapping live only in `transport.py`.

The integration imports `epcube_api`, which is not on PyPI. `scripts/build-release.sh`
vendors it into the HACS zip and rewrites the imports, so the source keeps one
home and only the artifact is bundled.

## One home per concept

A fact is defined once and imported everywhere else.

| Concept                     | Its one home                                                     |
| --------------------------- | ---------------------------------------------------------------- |
| Version                     | `pyproject.toml` = `manifest.json` = `epcube_api.__version__`    |
| Python version              | `.python-version` (interpreter), `requires-python` (floor)       |
| Minimum Home Assistant      | `hacs.json`                                                      |
| Configuration / environment | `.env.example`, read by `cli.py`, explained in `docs/setup.md`   |
| Protocol constants          | `epcube_api/const.py`: base URLs, user agent, enums              |
| API calls                   | `epcube_api/endpoints/`, one module per area                     |
| HTTP behaviour              | `epcube_api/transport.py`: retries, both error layers            |
| Response and request shapes | `epcube_api/models/`, pydantic                                   |
| Errors                      | `epcube_api/exceptions.py`                                       |
| The API surface             | `epcube_api/registry.py`, prose in `docs/api-endpoints.md`       |
| CLI copy                    | `epcube_api/cli.py`                                              |
| Integration copy            | `custom_components/epcube/strings.json` = `translations/en.json` |
| The "done" bar              | `scripts/verify.sh`                                              |
| License                     | `LICENSE`                                                        |

## Where new code goes

| You're adding                         | Put it in                                                      |
| ------------------------------------- | -------------------------------------------------------------- |
| A wrapper for an API route            | `epcube_api/endpoints/<area>.py`                               |
| A response shape                      | `epcube_api/models/<area>.py`                                  |
| A request body                        | `epcube_api/models/requests.py`                                |
| A newly discovered route              | `epcube_api/registry.py` **and** `docs/api-endpoints.md`       |
| A value coercion the API forces on us | `epcube_api/models/base.py`                                    |
| Cross-cutting HTTP behaviour          | `epcube_api/transport.py`                                      |
| A CLI command                         | `epcube_api/cli.py`                                            |
| Home Assistant glue                   | a flat module in `custom_components/epcube/`                   |
| A test                                | `tests/test_<area>.py`, shared fixtures in `tests/conftest.py` |

Integration modules stay flat: the release script rewrites `from epcube_api`
imports only in top-level `custom_components/epcube/*.py`.

An entity subclasses its platform base (`EpCubeSensorEntity`,
`EpCubeBinarySensorEntity`, `EpCubeNumberEntity`, `EpCubeSwitchEntity`) or
`EpCubeEntity` alone. Home Assistant narrows `entity_description` and
`_attr_device_class` in every platform class, and pyrefly strict rejects setting
them on a class with two entity parents; the empty bases exist so the class that
sets them has one. Keep a subclass's own description in `self._description`
rather than re-annotating `entity_description`.

# Invariants

- **A `switchMode` write is always a complete payload built from a fresh read.**
  The endpoint treats an absent field as "reset to default", so a partial body
  silently wipes the tariff calendar and both reserve levels. Go through
  `SwitchModeRequest.from_config(await client.device.mode(dev_id))` and
  `.with_changes(...)`; never hand-build the dict, and never add a field to that
  model without a default.
- **Field names are verified against a live response, never guessed.** The API's
  casing is not self-consistent (`backUpPower` but `backupLoadsMode`,
  `defTimeZone` but `devId`, `off_ON_Grid_Hint`, the misspelled
  `selfConsumptioinReserveSoc`). A wrong alias fails silently as `None`.
- **Every response model keeps unknown fields** (`extra="allow"` on
  `EpCubeModel`), so a firmware update adds data to `.extras` rather than
  losing it.
- **Both error layers are checked on every response.** The EU cluster uses HTTP
  status codes; US and JP answer HTTP 200 with the real code in the body's
  `status`. Reading only `response.status_code` turns an expired token there
  into an empty success.
- **A scope and its date format travel together.** Use `Scope.format_date`;
  a full date with `Scope.YEAR` is a server-side 500, not a validation error.
- **Only the live read may fail a snapshot.** Supplementary endpoints are
  best-effort and record into `Snapshot.errors`.
- **Test fixtures preserve the API's quirks**: numbers as strings, mixed casing,
  `workParam` as a JSON string, `hasValue` always 0. A tidied fixture protects
  nothing.
- **Coverage stays at 100%**, statements and branches (`--cov-fail-under=100`).
- **One version, three places.** Bump `pyproject.toml`, `manifest.json` (version
  and requirement) and `epcube_api.__version__` together; the release workflow
  refuses a tag that disagrees with any of them.
- **One Python.** The code targets 3.14 syntax (`except A, B:`), so the minimum
  Home Assistant in `hacs.json` is the first release on 3.14 (2026.3). Raising
  Python means raising that floor in the same change.
- **Secrets live in `.env` only**, which is gitignored; `.env.example` lists the
  variables with empty values. Never commit a token, a password or a real
  payload carrying the owner's address or coordinates.
- Lockfiles are committed and CI installs with `uv sync --locked`. Third-party
  actions are pinned to a commit SHA.

`scripts/check-invariants.py` enforces the style rules below; `scripts/check-secrets.sh`
catches credential-shaped strings. Everything else here needs review.

# Style

- **Comments: default zero.** Names, types and small functions carry the
  meaning. A comment survives only if it states, in one line, a constraint the
  code cannot express: an API quirk, a protocol rule, a security invariant, an
  order that looks wrong but is required. Never docstrings, banners, narration,
  history, TODOs or commented-out code. Tool directives (`# noqa`,
  `# type: ignore`, `# pyrefly: ignore`, `# pragma: no cover`, `# shellcheck`) don't
  count. `check-invariants` fails a file with a docstring, two comments on
  adjacent lines, or more than 2 comments. CI config (`.github/`) carries none.
- **Files stay under 400 lines**, tests included (`check-invariants` enforces
  it). Split by responsibility: a sibling module, or one test file per area.
- A rationale too long for one line belongs in `docs/`, not in the code.
- Match the surrounding naming and idiom. Reuse before you write; extend the
  existing module instead of forking a parallel one.
- Delete dead code rather than leaving it unused. No new barrel or
  re-export-only modules; the `__init__.py` of `epcube_api`, `models` and
  `endpoints` are the public surface and the only ones.
- Small and composable. One well-named function that does one thing.
- No em dashes anywhere, code or prose (`check-invariants` enforces it). Use a
  hyphen, a colon or parentheses.

# Naming

- Branches: `<type>/<kebab-summary>`, e.g. `feat/pv-string-sensors`.
- Commits and PR titles: Conventional Commits, `type(scope): imperative
  summary`, lowercase, ≤72 chars. Types: feat, fix, docs, refactor, perf, test,
  build, ci, chore, revert. CI rejects violations on PRs.
- Files: snake_case `.py` modules, kebab-case scripts in `scripts/`.
- Keep identifiers consistent across layers, so one concept reads the same in
  the model, the entity and its translation key.

# Git & PRs

- Commit and push only when asked. Don't commit as a side effect of finishing.
- Work on a branch off `main`; land through a squash-merged pull request so CI
  gates it. The PR title becomes the commit subject.
- A pre-commit hook (`.githooks/pre-commit`, wired by
  `git config core.hooksPath .githooks` or `.github/repo-setup.sh`) runs
  `scripts/verify.sh`. `--no-verify` only for a genuine WIP commit.
- Releases are tags: `v<version>` re-runs the bar, builds `epcube.zip` and
  publishes it; HACS installs releases only.
- The `main` ruleset requires the `ci` check; admins may bypass it, which is the
  exception, not the workflow. Never force-push `main`.

# Workflow

- Done means `sh scripts/verify.sh` is green: `check-secrets`,
  `check-invariants`, `ruff check`, `ruff format --check`, `pyrefly check`, `pytest`.
  CI runs the same script, then builds the HACS bundle and runs hassfest; the
  release adds HACS validation.
- Update `docs/` and both READMEs (`README.md`, `README-IT.md`) in the same
  change that alters behaviour or user-facing copy. `translations/en.json` is a
  copy of `strings.json`; change both.
- A change that touches the API is proven against a real system:
  `uv run epcube status`, `uv run epcube probe <path>`, or a running Home
  Assistant. The offline suite cannot tell a wrong sign or alias from a right one.
- `uv.lock` is generated: change dependencies in `pyproject.toml`, then `uv lock`.
  Dependabot bumps it and the pinned actions weekly after a seven-day cooldown.
