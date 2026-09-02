#!/bin/sh
# Build the HACS release zip: the integration with the client vendored into it.
#
# The integration imports `epcube_api`, which is not on PyPI, so a plain copy of
# custom_components/epcube would fail to load. Rather than publish the client
# separately or duplicate it in the repo, the release bundles it as a subpackage
# and rewrites the absolute imports to relative ones. The source keeps one home
# (epcube_api/); only the artifact is vendored.
#
#   sh scripts/build-release.sh [output.zip]
set -e

OUT=${1:-epcube.zip}

# CI has python3; a developer machine may only have the uv-managed one. Windows
# ships a python3 stub that resolves but refuses to run, so test execution, not
# just presence.
if python3 -c '' >/dev/null 2>&1; then
	PY="python3"
elif command -v uv >/dev/null 2>&1; then
	PY="uv run --frozen python"
else
	echo "need a working python3, or uv" >&2
	exit 1
fi
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

cp -r custom_components/epcube "$STAGE/epcube"
cp -r epcube_api "$STAGE/epcube/epcube_api"

find "$STAGE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -name '*.pyc' -delete 2>/dev/null || true

# `from epcube_api import X` -> `from .epcube_api import X`, and the same for
# submodule imports. Only the integration's own modules are touched: everything
# inside epcube_api already imports relatively.
for f in "$STAGE"/epcube/*.py; do
	sed -i.bak \
		-e 's/^from epcube_api import /from .epcube_api import /' \
		-e 's/^from epcube_api\./from .epcube_api./' \
		-e 's/^    from epcube_api import /    from .epcube_api import /' \
		-e 's/^    from epcube_api\./    from .epcube_api./' \
		"$f"
	rm -f "$f.bak"
done

if grep -rn '^\s*from epcube_api' "$STAGE/epcube"/*.py; then
	echo "FAIL: an absolute epcube_api import survived the rewrite" >&2
	exit 1
fi

# The client is inside the bundle now, so it must not also be a pip requirement.
# httpx ships with Home Assistant; pydantic does not.
$PY - "$STAGE/epcube/manifest.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    manifest = json.load(fh)
manifest["requirements"] = ["pydantic>=2.7"]
with open(path, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2)
    fh.write("\n")
print(f"requirements -> {manifest['requirements']}")
PY

# Prove the bundle imports as Home Assistant will load it, before shipping it.
$PY - "$STAGE" <<'PY'
import importlib
import sys

sys.path.insert(0, sys.argv[1])
module = importlib.import_module("epcube.epcube_api")
print(f"vendored client imports: epcube_api {module.__version__}")
PY

# Purge bytecode again: the import smoke test above regenerates it.
find "$STAGE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -name '*.pyc' -delete 2>/dev/null || true

# zipfile rather than zip(1): the latter is absent on a stock Windows dev box.
rm -f "$OUT"
$PY - "$STAGE" "$OUT" <<'ZIPPY'
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

stage, out = Path(sys.argv[1]), Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(out, "w", ZIP_DEFLATED) as archive:
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(stage).as_posix())
count = len(ZipFile(out).namelist())
print(f"OK {out} ({out.stat().st_size / 1024:.0f} KiB, {count} files)")
ZIPPY
