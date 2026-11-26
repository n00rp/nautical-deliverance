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
# Parts not yet built list their id prefix in the header; their requirements need no test yet.
PLANNED_MARKER = "- **Planned:** "


def _is_manual(spec: Path) -> bool:
    head = spec.read_text(encoding="utf-8").splitlines()[:20]
    return MANUAL_MARKER in head


def _planned(spec: Path) -> tuple[str, ...]:
    """Return the requirement id prefixes (e.g. B7b) the spec header lists as planned."""
    for line in spec.read_text(encoding="utf-8").splitlines()[:20]:
        if line.startswith(PLANNED_MARKER):
            return tuple(p.strip() for p in line[len(PLANNED_MARKER) :].split(","))
    return ()


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


def render(requirements: list[str], refs: dict[str, set[str]], planned: set[str]) -> str:
    """Render the traceability matrix, sorted by id then location."""
    rows = [
        f"| {r} | {', '.join(sorted(refs[r])) or ('planned' if r in planned else '')} |"
        for r in requirements
    ]
    head = ["# Traceability", "", "| Requirement | Referenced by |", "|---|---|"]
    return "\n".join([*head, *rows, ""])


def main(argv: list[str] | None = None) -> int:
    """Run the checker; return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--check", action="store_true", help="fail if the committed matrix differs")
    args = parser.parse_args(argv)
    root: Path = args.root

    found: set[str] = set()
    planned: set[str] = set()
    for spec in _files(root, "docs/superpowers/specs/*.md"):
        if _is_manual(spec):
            continue
        ids = SPEC_ROW.findall(spec.read_text(encoding="utf-8"))
        found.update(ids)
        prefixes = _planned(spec)
        planned.update(r for r in ids if r.split("-R")[0] in prefixes)
    requirements = sorted(found)
    refs = collect_refs(root)
    errors = [f"{r}: no test" for r in requirements if r not in refs and r not in planned]
    errors += [f"{r}: unknown requirement" for r in sorted(refs) if r not in requirements]
    matrix = render(requirements, refs, planned)
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
