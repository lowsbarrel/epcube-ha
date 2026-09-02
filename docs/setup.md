# Setup

Two audiences: someone turning the **template** into a project, and someone
setting up **local dev** on an existing clone.

## From template to project

The fast path is the `/setup` skill in Claude Code - it interviews you, replaces
every placeholder, wires the hook, and sets up the GitHub repo policy. To do it
by hand:

1. **Replace placeholders.** Grep for `{{` and substitute every double-brace
   token: `PROJECT_NAME`, `PROJECT_SLUG`, `DESCRIPTION`, `OWNER`. Confirm with
   `sh scripts/check-placeholders.sh`.
2. **Fill in [`../AGENTS.md`](../AGENTS.md)** - the "one home" tables and the
   Project invariants. This is the contract; don't skip it.
3. **Wire your stack.** Wire your linter and test runner into
   [`../scripts/verify.sh`](../scripts/verify.sh), enable the matching
   `dependabot.yml` ecosystem, and add a toolchain setup step to
   `.github/workflows/ci.yml` before it runs `scripts/verify.sh`.
4. **Wire the hook:** `git config core.hooksPath .githooks`.
5. **Set repo policy:** create the GitHub repo, then run
   `sh .github/repo-setup.sh` once as an admin (squash-only merges + the `main`
   ruleset that requires the `ci` check; it also wires the hook).
6. Delete the template callout at the top of `README.md`.

## Local dev

```sh
git config core.hooksPath .githooks   # wire the pre-commit hook (once per clone)
cp .env.example .env                   # fill in local config - never commit .env
sh scripts/verify.sh                   # the 'done' bar: secret scan + lint + tests
```

Add project-specific steps (install dependencies, start services, seed data) here
as you wire your stack.

## Requirements

List the tools a contributor needs (language runtime and version, package
manager, any services). Keep the versions in sync with what CI uses.
