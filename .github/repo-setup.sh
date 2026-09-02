#!/bin/sh
# Run once, locally, as a repo admin (gh auth login): sh .github/repo-setup.sh
# Applies merge hygiene + the branch ruleset that CI depends on. Idempotent.
set -e

command -v gh >/dev/null 2>&1 || { echo "gh (GitHub CLI) is required: https://cli.github.com"; exit 1; }
repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)

# Wire the local pre-commit hook (safe to re-run).
git config core.hooksPath .githooks
echo "hooks: core.hooksPath → .githooks"

gh api -X PATCH "repos/$repo" \
	-F allow_merge_commit=false \
	-F allow_rebase_merge=false \
	-F allow_squash_merge=true \
	-f squash_merge_commit_title=PR_TITLE \
	-f squash_merge_commit_message=PR_BODY \
	-F delete_branch_on_merge=true >/dev/null
echo "merge settings: squash-only, PR title as subject, branches auto-deleted"

ruleset_id=$(gh api "repos/$repo/rulesets" --jq '.[] | select(.name=="main") | .id' | head -n1)
if [ -n "$ruleset_id" ]; then
	gh api -X PUT "repos/$repo/rulesets/$ruleset_id" --input .github/rulesets/main.json >/dev/null
	echo "ruleset updated from .github/rulesets/main.json"
else
	gh api -X POST "repos/$repo/rulesets" --input .github/rulesets/main.json >/dev/null
	echo "ruleset created from .github/rulesets/main.json"
fi
echo "done: $repo"
