#!/bin/sh
set -e

echo "verify ▸ check-secrets"
sh scripts/check-secrets.sh

echo "verify ▸ check-invariants"
uv run --locked --group homeassistant python scripts/check-invariants.py

echo "verify ▸ lint"
uv run --locked --group homeassistant ruff check .
uv run --locked --group homeassistant ruff format --check .

echo "verify ▸ types"
uv run --locked --group homeassistant pyrefly check

echo "verify ▸ test"
uv run --locked --group homeassistant pytest tests

echo "✓ verify - all checks passed"
