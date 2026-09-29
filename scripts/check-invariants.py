import ast
import io
import re
import subprocess
import sys
import tokenize
from itertools import pairwise
from pathlib import Path

MAX_LINES = 400
MAX_COMMENTS = 2
SOURCE = {".py", ".sh", ".toml", ".yml", ".yaml", ".json"}
HASH_COMMENTED = {".sh", ".toml", ".yml", ".yaml"}
DIRECTIVE = re.compile(r"#\s*(noqa|type:|pyrefly:|pragma:|fmt:|ruff:|pyright:|shellcheck\s)")
QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
DOC_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
EM_DASH = "\u2014"

violations: list[str] = []


def tracked() -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [p for p in map(Path, listing.splitlines()) if p.is_file()]


def check_dashes(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    violations.extend(
        f"{path.as_posix()}:{number}: em dash - use a hyphen, colon or parentheses"
        for number, line in enumerate(text.splitlines(), 1)
        if EM_DASH in line
    )


def is_hook(path: Path) -> bool:
    return path.parent.name == ".githooks"


def python_comments(code: str) -> list[tuple[int, str]]:
    tokens = tokenize.generate_tokens(io.StringIO(code).readline)
    return [(t.start[0], t.string) for t in tokens if t.type == tokenize.COMMENT]


def hash_comments(code: str) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(code.splitlines(), 1):
        bare = QUOTED.sub("", line)
        match = re.search(r"(^|\s)#", bare)
        if match:
            found.append((number, bare[match.end() - 1 :]))
    return found


def docstrings(code: str) -> list[int]:
    return [
        node.body[0].lineno
        for node in ast.walk(ast.parse(code))
        if isinstance(node, DOC_OWNERS)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ]


def check(path: Path) -> None:
    name = path.as_posix()
    code = path.read_text(encoding="utf-8")
    lines = len(code.splitlines())
    if lines > MAX_LINES:
        violations.append(f"{name}: {lines} lines - split it by responsibility (limit {MAX_LINES})")
    if path.suffix == ".py":
        violations.extend(
            f"{name}:{line}: docstring - names and types document the code"
            for line in docstrings(code)
        )
        found = python_comments(code)
    elif path.suffix in HASH_COMMENTED or is_hook(path):
        found = hash_comments(code)
    else:
        return
    comments = [
        (number, text)
        for number, text in found
        if not DIRECTIVE.match(text) and not (number == 1 and text.startswith("#!"))
    ]
    if name.startswith(".github/"):
        violations.extend(f"{name}:{n}: comment in CI config - none allowed" for n, _ in comments)
        return
    adjacent = next((b for (a, _), (b, _) in pairwise(comments) if b == a + 1), None)
    if adjacent:
        violations.append(f"{name}:{adjacent}: multi-line comment - one line, if it exists at all")
    if len(comments) > MAX_COMMENTS:
        violations.append(
            f"{name}: {len(comments)} comments (limit {MAX_COMMENTS}) - keep only real constraints"
        )


for path in tracked():
    check_dashes(path)
    if path.suffix in SOURCE or is_hook(path):
        check(path)

if violations:
    print("✖ check:invariants - AGENTS.md invariant violations:\n", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    sys.exit(1)
print("✓ check:invariants - no violations")
