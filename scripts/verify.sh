#!/bin/sh
# The 'done' bar - the one home for "what must pass". The pre-commit hook and CI
# both run this, so a green local run predicts a green PR.
set -e

echo "verify ▸ check-secrets"
sh scripts/check-secrets.sh

echo "verify ▸ lint"
uv run --locked ruff check .
uv run --locked ruff format --check .

echo "verify ▸ types"
uv run --locked ty check

echo "verify ▸ test"
uv run --locked pytest

echo "✓ verify - all checks passed"
