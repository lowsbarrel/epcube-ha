#!/bin/sh
# The 'done' bar - the one home for "what must pass". The pre-commit hook and CI
# both run this, so a green local run predicts a green PR.
set -e

echo "verify ▸ check-secrets"
sh scripts/check-secrets.sh

echo "verify ▸ lint"
uv run --frozen ruff check .
uv run --frozen ruff format --check .

echo "verify ▸ types"
uv run --frozen ty check

echo "verify ▸ test"
uv run --frozen pytest

echo "✓ verify - all checks passed"
