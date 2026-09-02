#!/bin/sh
# Fails if any all-caps double-brace identity token from the template survives.
# Only all-caps tokens like {{PROJECT_NAME}} are enforced; the prose guidance
# placeholders in AGENTS.md (e.g. {{FILL IN}}, {{service layer}}) contain spaces
# or lowercase and are ignored by design. The .claude/ setup skill documents the
# mechanism, so it is excluded too.
set -e

if git grep -InE '\{\{[A-Z0-9_]+\}\}' -- ':!.claude' ':!scripts/check-placeholders.sh'; then
	echo ""
	echo "✖ check:placeholders - the template placeholders above were never replaced."
	echo "  Run the /setup skill, or grep for '{{' and fill each one in."
	exit 1
fi
echo "✓ check:placeholders - none remaining"
