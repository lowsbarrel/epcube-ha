#!/bin/sh
set -e

OUT=${1:-epcube.zip}

# Windows ships a python3 stub that resolves but refuses to run, so probe by executing it.
if command -v uv >/dev/null 2>&1; then
	PY="uv run --locked python"
elif python3 -c '' >/dev/null 2>&1; then
	PY="python3"
else
	echo "need uv, or a working python3" >&2
	exit 1
fi
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

cp -r custom_components/epcube "$STAGE/epcube"
cp -r epcube_api "$STAGE/epcube/epcube_api"

purge_bytecode() {
	find "$STAGE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
	find "$STAGE" -name '*.pyc' -delete 2>/dev/null || true
}
purge_bytecode

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

$PY - "$STAGE" <<'PY'
import importlib
import sys
import types

parent = types.ModuleType("epcube")
parent.__path__ = [f"{sys.argv[1]}/epcube"]
sys.modules["epcube"] = parent

module = importlib.import_module("epcube.epcube_api")
print(f"vendored client imports: epcube_api {module.__version__}")
PY

purge_bytecode

# HACS extracts the zip verbatim into custom_components/epcube/, so the manifest must sit at its root.
rm -f "$OUT"
$PY - "$STAGE/epcube" "$OUT" <<'ZIPPY'
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

stage, out = Path(sys.argv[1]), Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(out, "w", ZIP_DEFLATED) as archive:
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(stage).as_posix())
names = ZipFile(out).namelist()
if "manifest.json" not in names:
    print("FAIL: manifest.json is not at the zip root", file=sys.stderr)
    sys.exit(1)
print(f"OK {out} ({out.stat().st_size / 1024:.0f} KiB, {len(names)} files)")
ZIPPY
