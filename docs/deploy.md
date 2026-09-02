# Deploy

## CI/CD

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on every PR and
every push to the default branch:

- **conventions** - PR title and commit messages must be Conventional Commits
  (≤72 chars). Zero-dependency inline checks; PR titles are treated as untrusted
  input.
- **verify** - the placeholder guard and `sh scripts/verify.sh` (secret scan +
  lint + test).
- **ci** - an aggregate gate that `needs` every blocking job. This is the _single_
  required status check in the branch ruleset, so adding a new required job means
  adding it to this job's `needs` (one home) - no ruleset edit needed.

Add your deploy job to `ci.yml` (typically `if: github.event_name == 'push' &&
github.ref == 'refs/heads/main'`, gated behind `needs: [verify]`) and store its
credentials as GitHub Actions secrets - never in the repo.

## Repo policy as code

Branch protection and merge settings live in the repo, not in someone's memory:

- [`.github/rulesets/main.json`](../.github/rulesets/main.json) - the default-branch
  ruleset: no deletion, no force-push, PRs required, and the `ci` check required.
- [`.github/repo-setup.sh`](../.github/repo-setup.sh) - applies that ruleset plus
  squash-only merges (PR title as the subject, branches auto-deleted). Run once as
  an admin; re-run any time the ruleset changes. It's idempotent.

Repo admins can bypass the ruleset, so a solo maintainer isn't locked out - but
the default path is PR + green CI + squash merge.

## Releasing

Record your release process here (versioning, tags, and how you cut a release) if
the project ships versioned artifacts. If it's a continuously deployed service,
say so - the merge-to-default-branch → deploy pipeline above is the release.
