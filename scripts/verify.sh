#!/bin/sh
set -e

echo "verify ▸ check-secrets"
sh scripts/check-secrets.sh

echo "verify ▸ check-invariants"
uv run --locked python scripts/check-invariants.py

echo "verify ▸ lint"
uv run --locked ruff check .
uv run --locked ruff format --check .

echo "verify ▸ types"
uv run --locked pyrefly check

echo "verify ▸ test"
uv run --locked pytest

echo "✓ verify - all checks passed"
