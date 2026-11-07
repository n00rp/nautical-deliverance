"""Requirement traceability: every spec requirement needs at least one test (D-036, S0-R09)."""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ID = r"(?:S\d\w*|C\d+|B\d+[a-z]?)-R\d{2}"
SPEC_ROW = re.compile(rf"^\| ({ID}) \|", re.MULTILINE)
PY_REF = re.compile(r'req\("([^"]+)"\)')
TS_REF = re.compile(rf"\[({ID})\]")
YAML_REF = re.compile(r"#\s*req:(.*)")
MATRIX = "docs/traceability.md"
# Specs verified by owner review, not code (design documents), opt out in their header.
MANUAL_MARKER = "- **Traceability:** manual"


def _is_manual(spec: Path) -> bool:
    head = spec.read_text(encoding="utf-8").splitlines()[:20]
    return MANUAL_MARKER in head


def _files(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern))


def collect_refs(root: Path) -> dict[str, set[str]]:
    """Map referenced id -> repo-relative POSIX paths that reference it."""
    refs: dict[str, set[str]] = defaultdict(set)
    sources = [
        (_files(root, "engine/tests/**/*.py") + _files(root, "tools/test_*.py"), PY_REF),
        (
            _files(root, "web/src/**/*.test.ts")
            + _files(root, "web/src/**/*.test.tsx")
            + _files(root, "web/e2e/**/*.spec.ts"),
            TS_REF,
        ),
    ]
    for paths, rx in sources:
        for path in paths:
            for found in rx.findall(path.read_text(encoding="utf-8")):
                refs[found].add(path.relative_to(root).as_posix())
    # CI workflows and the test scripts (`# req: ...` comment) that run in them.
    for path in _files(root, ".github/workflows/*.yml") + _files(root, "tools/test_*.sh"):
        for line in YAML_REF.findall(path.read_text(encoding="utf-8")):
            for found in line.split():
                refs[found].add(path.relative_to(root).as_posix())
    return refs


def render(requirements: list[str], refs: dict[str, set[str]]) -> str:
    """Render the traceability matrix, sorted by id then location."""
    rows = [f"| {r} | {', '.join(sorted(refs[r]))} |" for r in requirements]
    head = ["# Traceability", "", "| Requirement | Referenced by |", "|---|---|"]
    return "\n".join([*head, *rows, ""])


def main(argv: list[str] | None = None) -> int:
    """Run the checker; return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--check", action="store_true", help="fail if the committed matrix differs")
    args = parser.parse_args(argv)
    root: Path = args.root

    requirements = sorted(
        {
            m
            for spec in _files(root, "docs/superpowers/specs/*.md")
            if not _is_manual(spec)
            for m in SPEC_ROW.findall(spec.read_text(encoding="utf-8"))
        }
    )
    refs = collect_refs(root)
    errors = [f"{r}: no test" for r in requirements if r not in refs]
    errors += [f"{r}: unknown requirement" for r in sorted(refs) if r not in requirements]
    matrix = render(requirements, refs)
    target = root / MATRIX
    if args.check and (not target.exists() or target.read_text(encoding="utf-8") != matrix):
        errors.append(f"{MATRIX} is out of date; run `python tools/trace.py`")
    for error in errors:
        print(error, file=sys.stderr)  # noqa: T201
    if errors:
        return 1
    if not args.check:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(matrix, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
