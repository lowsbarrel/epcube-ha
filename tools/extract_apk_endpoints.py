#!/usr/bin/env python3
"""Pull API endpoint strings out of the EP Cube Android APK.

The integration only knows the handful of endpoints its author happened to
observe. The app knows all of them, and Dalvik bytecode stores string literals
verbatim in the .dex string table -- so the full list can be read without a
decompiler, an emulator, or a proxy.

    uv run tools/extract_apk_endpoints.py path\\to\\epcube.apk

Works on .apk and .xapk/.apkm bundles (they are just zips of zips).
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

# Paths the API uses: /device/..., /user/..., /open/common/..., plus anything
# that looks like a REST route with a camelCase verb.
PATH_RE = re.compile(
    rb"/(?:device|user|open|common|app|sys|data|home|energy|statistic|report)"
    rb"[A-Za-z0-9_/\-]{2,80}"
)
# Loose net for anything else route-shaped, e.g. "queryDataElectricityV2"
VERB_RE = re.compile(rb"\b(?:query|get|list|fetch|load|read)[A-Z][A-Za-z0-9]{3,40}\b")

INTERESTING = re.compile(
    r"chart|curve|line|history|trend|detail|day|hour|minute|power|electric|"
    r"energy|data|statistic|report|graph",
    re.I,
)


def iter_dex(path: Path):
    """Yield (name, bytes) for every .dex in the apk, including nested apks."""
    with zipfile.ZipFile(path) as archive:
        for entry in archive.namelist():
            if entry.endswith(".dex"):
                yield entry, archive.read(entry)
            elif entry.endswith((".apk", ".xapk", ".apkm")):
                # split APKs / bundles: recurse one level
                nested = io.BytesIO(archive.read(entry))
                try:
                    with zipfile.ZipFile(nested) as inner:
                        for sub in inner.namelist():
                            if sub.endswith(".dex"):
                                yield f"{entry}!{sub}", inner.read(sub)
                except zipfile.BadZipFile:
                    continue
            # Flutter / React Native apps keep their code here instead
            elif entry.endswith((".bundle", "libapp.so", "index.android.bundle")):
                yield entry, archive.read(entry)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("apk", type=Path)
    parser.add_argument(
        "--all",
        action="store_true",
        help="list every path found, not just the likely-interesting ones",
    )
    args = parser.parse_args()

    if not args.apk.is_file():
        print(f"no such file: {args.apk}", file=sys.stderr)
        return 1

    paths = Counter()
    verbs = Counter()
    scanned = 0

    for name, blob in iter_dex(args.apk):
        scanned += 1
        print(f"scanning {name} ({len(blob):,} bytes)", file=sys.stderr)
        for match in PATH_RE.findall(blob):
            paths[match.decode("utf-8", "replace")] += 1
        for match in VERB_RE.findall(blob):
            verbs[match.decode("utf-8", "replace")] += 1

    if not scanned:
        print("no .dex found -- is this really an APK?", file=sys.stderr)
        return 1

    known = {
        "/device/homeDeviceInfo",
        "/device/getSwitchMode",
        "/device/switchMode",
        "/device/userDeviceInfo",
        "/device/deviceList",
        "/device/queryDataElectricityV2",
        "/user/user/base",
        "/open/common/login",
        "/open/common/captcha/get",
        "/open/common/captcha/check",
    }

    print()
    print("=" * 72)
    print(f"API paths found: {len(paths)}")
    print("=" * 72)
    for path in sorted(paths):
        if not args.all and not INTERESTING.search(path) and path not in known:
            continue
        tag = "  [known]" if path in known else ""
        print(f"  {path:<58} x{paths[path]}{tag}")

    new = sorted(p for p in paths if p not in known)
    print()
    print(f"not used by the integration: {len(new)}")

    print()
    print("=" * 72)
    print("query-ish method names (hints at endpoints built at runtime)")
    print("=" * 72)
    for verb in sorted(verbs):
        if INTERESTING.search(verb):
            print(f"  {verb:<58} x{verbs[verb]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
