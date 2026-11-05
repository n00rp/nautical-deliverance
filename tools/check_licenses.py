"""Dependency license gate (S0-R10): fail on any license outside the allow-list."""

import argparse
import json
import re
import sys
from pathlib import Path

# D-044 added MIT-0, CC0-1.0, BlueOak-1.0.0 and Python-2.0; D-061 added 0BSD and Zlib.
# LGPL is allowed for unmodified dynamic use only.
ALLOWED = {
    "MIT", "MIT-0", "CC0-1.0", "BlueOak-1.0.0", "Python-2.0",
    "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "PSF-2.0", "MPL-2.0",
    "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later", "0BSD", "Zlib",
}  # fmt: skip


class _BadExpressionError(Exception):
    """Malformed license expression."""


# Trove-classifier names pip-licenses reports when a package has no SPDX expression.
# "BSD License" is BSD-2 or BSD-3 (both allowed); 4-clause BSD is not realistic in PyPI today.
TROVE = {
    "MIT License": "MIT",
    "BSD License": "BSD-3-Clause",
    "Apache Software License": "Apache-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "ISC License (ISCL)": "ISC",
    "GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.1-or-later",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
}
TOKEN = re.compile(r"\(|\)|[^\s()]+")


def _parse_or(tokens: list[str]) -> bool:
    ok = _parse_and(tokens)
    while tokens and tokens[0].upper() == "OR":
        tokens.pop(0)
        ok = _parse_and(tokens) or ok  # always consume the right side
    return ok


def _parse_and(tokens: list[str]) -> bool:
    ok = _parse_atom(tokens)
    while tokens and tokens[0].upper() == "AND":
        tokens.pop(0)
        ok = _parse_atom(tokens) and ok
    return ok


def _parse_atom(tokens: list[str]) -> bool:
    if not tokens:
        raise _BadExpressionError
    tok = tokens.pop(0)
    if tok == "(":
        ok = _parse_or(tokens)
        if not tokens or tokens.pop(0) != ")":
            raise _BadExpressionError
        return ok
    if tok in {")", "AND", "OR"} or tok.upper() in {"AND", "OR", "WITH"}:
        raise _BadExpressionError
    return tok in ALLOWED


def is_allowed(expression: str) -> bool:
    """Return True if the SPDX expression is satisfiable using only allowed licenses."""
    tokens = TOKEN.findall(TROVE.get(expression.strip(), expression))
    try:
        ok = _parse_or(tokens)
    except _BadExpressionError:
        return False
    return ok and not tokens  # leftovers (e.g. WITH exceptions, junk words) => unknown => fail


def _packages(pip_path: Path | None, pnpm_path: Path | None) -> list[tuple[str, str, str]]:
    """(ecosystem, package, license) triples."""
    found: list[tuple[str, str, str]] = []
    if pip_path:
        data = json.loads(pip_path.read_text(encoding="utf-8-sig"))
        found += [("pip", p["Name"], p.get("License", "")) for p in data]
    if pnpm_path:
        data = json.loads(pnpm_path.read_text(encoding="utf-8-sig"))
        found += [("pnpm", p["name"], lic) for lic, pkgs in data.items() for p in pkgs]
    return found


def main(argv: list[str] | None = None) -> int:
    """Run the checker; return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pip", type=Path, help="pip-licenses --format=json output")
    parser.add_argument("--pnpm", type=Path, help="pnpm licenses list --json output")
    parser.add_argument("--approved", type=Path, help="owner-approved package names, one per line")
    args = parser.parse_args(argv)

    approved: set[str] = set()
    if args.approved:
        lines = args.approved.read_text(encoding="utf-8").splitlines()
        approved = {s for ln in lines if (s := ln.split("#")[0].strip())}

    bad = [
        f"{eco}: {name}: {lic or '<empty>'}"
        for eco, name, lic in _packages(args.pip, args.pnpm)
        if name not in approved and not is_allowed(lic)
    ]
    for line in sorted(set(bad)):
        sys.stdout.write(f"DISALLOWED LICENSE {line}\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
