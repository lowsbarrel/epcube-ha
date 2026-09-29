# Deploy

## Branching

Trunk-based, and deliberately plain: one long-lived branch, `main`.

- Work happens on a short-lived branch off `main`, named `<type>/<kebab-summary>`.
- It lands through a **pull request**, squash-merged, branch deleted after.
- There is **no staging branch, no develop branch, no release branch.** A release
  is a tag on `main`, nothing more.
- The default-branch ruleset requires a PR with the `ci` check green. Repo admins
  can bypass it, so a solo maintainer is never locked out, but that is the
  exception, not the workflow.

## CI

[`ci.yml`](../.github/workflows/ci.yml) runs on every PR and every push to `main`:

| Job | What it does |
| --- | --- |
| `conventions` | PR title and every commit message must be Conventional Commits, ≤72 chars |
| `verify` | `uv sync --locked`, `sh scripts/verify.sh`, then builds the HACS bundle |
| `hassfest` | Home Assistant's own manifest and translation validation |
| `ci` | the aggregate gate |

`ci` is the **single required status check** in the ruleset, and it `needs` every
blocking job. Adding a new required job means adding it to that `needs` list:
one home, no ruleset edit, no re-running `repo-setup.sh`.

The interpreter comes from `.python-version` (3.14), so CI never drifts to a
Python that Home Assistant does not run yet. Third-party actions are pinned to a
commit SHA and carry no comments; Dependabot bumps them, and the `uv` lockfile,
weekly after a seven-day cooldown.

HACS validation runs in `release.yml`, after the release is published: with
`zip_release` set, HACS reads the manifest out of the release zip, so validating
before one exists reports a missing manifest. It runs with no ignored checks,
which is what inclusion in the HACS default store requires. The brands check
passes because `epcube` is registered in `home-assistant/brands` (shared with
`Bobsilvio/epcube`, which uses the same domain).

## Releasing

HACS is wired to releases only (`hide_default_branch` in
[`hacs.json`](../hacs.json)), so nothing reaches a user until a tag is pushed.
**Merging to `main` ships nothing.**

To cut a release:

1. Bump the version in `pyproject.toml`, `custom_components/epcube/manifest.json`
   (`version` and the `epcube-api` requirement) and `epcube_api/__init__.py`,
   then run `uv lock`. They must agree with the tag; the workflow refuses to
   build otherwise, because a mismatch would make Home Assistant report a
   different version from the one HACS installed.
2. Land that through a PR like anything else.
3. Tag and push:

   ```sh
   git tag v0.2.0 && git push origin v0.2.0
   ```

[`release.yml`](../.github/workflows/release.yml) then re-runs the full
verification bar, builds the bundle, and publishes the release with generated
notes. A `workflow_dispatch` run can rebuild an existing tag.

## The release bundle

[`scripts/build-release.sh`](../scripts/build-release.sh) produces `epcube.zip`:
`custom_components/epcube/` with `epcube_api/` vendored inside it and the
absolute imports rewritten to relative ones.

It exists because the integration imports `epcube_api`, which is not published to
PyPI, so a bare copy of the source folder would fail to load. Bundling keeps the
source with **one home** (`epcube_api/`) while making the artifact
self-contained: the only thing Home Assistant installs is `pydantic`, since httpx
already ships with it.

The script verifies its own output before zipping. It fails if any absolute
`epcube_api` import survived the rewrite, and it imports the vendored client
under the name Home Assistant will use. That import runs under `uv`, so the
client's dependencies are there, and it substitutes a placeholder for the
integration package instead of executing the real one, which would drag Home
Assistant itself into the build. CI runs the same script on every pull request,
so a bundle that cannot be built is caught long before a tag exists. Run it
locally any time:

```sh
sh scripts/build-release.sh
```

If the client is ever published to PyPI, this step disappears: the manifest would
just declare `epcube-api==<version>` and the zip would be the integration folder
alone.

## Repo policy as code

- [`.github/rulesets/main.json`](../.github/rulesets/main.json) is the
  default-branch ruleset: PRs required, `ci` must pass.
- [`.github/repo-setup.sh`](../.github/repo-setup.sh) applies squash-only merges,
  the PR title as the squash subject, branch auto-deletion, and the ruleset.
  Idempotent; run once as an admin.
