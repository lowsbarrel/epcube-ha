# Engineering conventions

The contract for anyone - human or AI - who changes this repository. Read it
before adding a file, and search for an existing home before creating a new one.
It is deliberately stack-agnostic: fill the `{{…}}` placeholders and the
**Project invariants** section with what is true for _this_ project, then delete
the guidance that does not apply.

> Companion files: [`README.md`](README.md) is the human front door and
> [`docs/`](docs/) holds the long-form explanations. This file is the terse,
> load-bearing summary they point back to.

# Code organization

Keep the codebase clean by giving each thing **one home** and reusing it - never
restating a fact that already lives somewhere.

## One home per concept (the anti-redundancy rule)

A fact is defined once and imported everywhere else - never copied, never
restated. **Derive instead of duplicating.** If you write the same value or rule
in two places, one of them is a bug waiting to happen - collapse it to one.

Keep a table of the concepts that matter in _this_ project and where each one
lives, so the next person (or agent) can find the home instead of forking a
parallel copy:

| Concept                        | Its one home                                          |
| ------------------------------ | ----------------------------------------------------- |
| Public identity (name, URL)    | `pyproject.toml`, surfaced in `README.md`             |
| Configuration / environment    | `.env.example` (the documented list), read by `cli.py` |
| Protocol constants             | `epcube_api/const.py` - base URLs, user agent, enums   |
| Domain logic (API calls)       | `epcube_api/endpoints/`, one module per area           |
| HTTP behaviour                 | `epcube_api/transport.py` - retries, both error layers |
| Input validation / data model  | `epcube_api/models/`, pydantic                         |
| Error definitions              | `epcube_api/exceptions.py`                             |
| The API surface itself         | `epcube_api/registry.py`, prose in `docs/api-endpoints.md` |
| User-facing copy               | `epcube_api/cli.py`                                    |

## Where new code goes

Decide the home _before_ writing code, and record the rule here so it holds for
everyone after you:

| You're adding                            | Put it in                                     |
| ---------------------------------------- | --------------------------------------------- |
| A wrapper for an API route               | `epcube_api/endpoints/<area>.py`              |
| A response shape                         | `epcube_api/models/<area>.py`                 |
| A request body                           | `epcube_api/models/requests.py`               |
| A newly discovered route                 | `epcube_api/registry.py` **and** `docs/api-endpoints.md` |
| A value coercion the API forces on us    | `epcube_api/models/base.py`                   |
| Cross-cutting HTTP behaviour             | `epcube_api/transport.py`                     |
| A command                                | `epcube_api/cli.py`                           |
| Home Assistant glue                      | `custom_components/epcube/`                   |

## Stay clean

- **Reuse before you write.** Find an existing function, helper, or component and
  extend it; don't fork a parallel path.
- **Delete, don't accumulate.** Remove dead code instead of leaving it unused.
  Anything shipped as an example is a reference to delete, not a foundation to
  copy. No barrel/re-export-only files.
- **Match the surroundings** in naming and idiom, but keep comments minimal. A
  comment earns its place only by stating a load-bearing constraint that isn't
  obvious from the code, in one terse line - never narrate what the next line
  does. Prefer writing/extending a doc over adding a comment block.
- **Small and composable.** One well-named function that does one thing beats a
  branchy monolith.

# Invariants

These hold everywhere and don't get re-litigated per change. The first block is
universal; the second is yours to make concrete.

## Universal

- **Secrets never enter the repo.** No credentials, tokens, private keys, or
  `.env*` files (except `.env.example`) in git. They come from the environment or
  a secret manager. `scripts/check-secrets.sh` blocks the obvious ones in the
  pre-commit hook and CI, but it catches mechanical slips only.
- **Never trust input.** Validate and authorize at the boundary; a downstream
  layer must not assume an upstream one already checked.
- **Never leak internals to clients.** Surface a typed/coded error; don't return
  a raw stack trace or internal message.
- **Fail closed.** When a security-relevant check errors or is unconfigured, deny
  rather than allow.
- **Placeholders are replaced before launch.** Any remaining `{{…}}` token is an
  unfinished setup step; `scripts/check-placeholders.sh` enforces this in CI.
- **The lockfile / pinned dependencies are committed** and CI installs from them
  frozen - reproducible builds, closed supply chain. Pin third-party CI actions
  to a commit SHA.

## Project invariants

These are specific to this project and are not re-litigated per change.

- **A `switchMode` write is always a complete payload built from a fresh read.**
  The endpoint treats an absent field as "reset to default", so a partial body
  silently wipes the tariff calendar and both reserve levels. Go through
  `SwitchModeRequest.from_config(await client.device.mode(dev_id))` and
  `.with_changes(...)`; never hand-build the dict, and never add a field to that
  model without a default.
- **Field names are verified against a live response, never guessed.** The API's
  casing is not self-consistent (`backUpPower` but `backupLoadsMode`,
  `defTimeZone` but `devId`, `off_ON_Grid_Hint`, the misspelled
  `selfConsumptioinReserveSoc`). A wrong alias fails silently as `None`. Diff the
  model against a real payload before shipping a new field.
- **Every response model keeps unknown fields** (`extra="allow"` on
  `EpCubeModel`), so a firmware update adds data rather than losing it. Check
  `.extras` when something new appears.
- **Both error layers are checked on every response.** The EU cluster uses HTTP
  status codes; US and JP answer HTTP 200 with the real code in the body's
  `status`. Anything reading only `response.status_code` treats an expired token
  there as an empty success.
- **A scope and its date format travel together.** Use `Scope.format_date`;
  passing a full date with `Scope.YEAR` is a server-side 500, not a validation
  error.
- **Only the live read may fail a snapshot.** Supplementary endpoints are
  best-effort and record into `Snapshot.errors`; one slow statistics route must
  never take the live data down with it.
- **Test fixtures preserve the API's quirks** - numbers as strings, mixed casing,
  `workParam` as a JSON string, `hasValue` always 0. A fixture that tidies those
  up stops protecting anything.
- **Secrets live in `.env` only**, which is gitignored; `.env.example` documents
  the variables with empty values.

# Naming

- **Branches:** `<type>/<kebab-summary>`, e.g. `feat/user-invites`.
- **Commits and PR titles:** [Conventional Commits](https://www.conventionalcommits.org) -
  `type(scope): imperative summary`, lowercase, ≤72 chars. Types: `feat`, `fix`,
  `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`. CI
  rejects violations on PRs, and the PR title becomes the squash-merge subject.
- **Files:** pick one convention per language and hold it (e.g. `kebab-case`
  source files, `PascalCase` components). Record the choice; don't mix.
- Keep identifiers consistent across layers so one concept reads the same
  everywhere.

# Git & PRs

- **Commit and push only when asked.** Don't create commits as a side effect of
  finishing a change.
- **Work on a branch off the default branch** (`<type>/<kebab-summary>`) - never
  commit directly to it. Land work through a **pull request**; that is where CI
  gates it.
- **Keep commits small and each one a passing state.** An enforced pre-commit
  hook (`.githooks/pre-commit`, wired by `git config core.hooksPath .githooks` -
  `.github/repo-setup.sh` does this) runs the project's verification bar before
  every commit; `--no-verify` is for a genuine work-in-progress only.
- **Open the PR** with a Conventional-Commit title (it becomes the squashed
  subject) and a body that says _what changed and why_. Don't merge until checks
  are green; verify the change in the real runtime (preview/staging) where one
  exists.
- **Merge is squash-only** with the PR title as the subject (set by
  `.github/repo-setup.sh`). Delete the branch after.
- The default-branch ruleset requires PRs with green checks; repo **admins may
  bypass** it, so a solo maintainer _may_ push straight to the default branch
  when they explicitly choose. That's the exception, not the default.
- Never commit secrets or `.env*`; never force-push the default branch.

# Workflow

- **Done means** every gate in the project's verification bar is green - the same
  set the pre-commit hook and CI run. Define that set once (in `scripts/verify.sh`,
  which both call) so "done" has one meaning.
- Update the docs (`docs/`) and user-facing copy in the same change that alters
  behavior - not in a follow-up.
- Generated files are committed but never hand-edited; regenerate them with their
  generator. List which files are generated in `.gitattributes`
  (`linguist-generated`).
- Mechanical checks (`check:secrets`, `check:placeholders`, and any
  `check:invariants` you add) catch slips only; logic and reasoning bugs still
  need tests and review. Run a review pass over the diff before merging.
