#!/bin/sh
# Zero-dependency secret scanner over tracked files. Runs in the pre-commit hook
# and in CI. Catches common credential shapes only - it is a backstop, not a
# guarantee. Portable POSIX sh; needs only git + grep.
set -e

FOUND=0

# Paths that legitimately hold hashes/blobs and would only cause false positives.
EXCLUDES="
:!scripts/check-secrets.sh
:!*.png :!*.jpg :!*.jpeg :!*.gif :!*.ico :!*.svg :!*.webp :!*.woff :!*.woff2 :!*.pdf
:!*.lock :!pnpm-lock.yaml :!package-lock.json :!yarn.lock :!bun.lock :!Cargo.lock :!go.sum :!poetry.lock
"

scan() { # $1 = label, $2 = extended regex
	# shellcheck disable=SC2086
	matches=$(git grep -InE "$2" -- $EXCLUDES 2>/dev/null || true)
	if [ -n "$matches" ]; then
		printf '  %s:\n' "$1"
		printf '%s\n' "$matches" | sed 's/^/    /'
		FOUND=1
	fi
}

scan "private key"          '-----BEGIN( RSA| EC| OPENSSH| DSA)? PRIVATE KEY-----'
scan "AWS access key id"    'AKIA[0-9A-Z]{16}'
scan "Google OAuth secret"  'GOCSPX-[A-Za-z0-9_-]{20,}'
scan "Stripe secret key"    'sk_(live|test)_[A-Za-z0-9]{16,}'
scan "Slack token"          'xox[baprs]-[A-Za-z0-9-]{10,}'
scan "GitHub token"         'gh[pousr]_[A-Za-z0-9]{30,}'
scan "generic API key/JWT"  'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'

if [ "$FOUND" -ne 0 ]; then
	echo ""
	echo "✖ check:secrets - potential secrets in tracked files (above)."
	echo "  Rotate the credential immediately if real. If it is a false positive,"
	echo "  refine scripts/check-secrets.sh."
	exit 1
fi
echo "✓ check:secrets - no tracked secrets"
