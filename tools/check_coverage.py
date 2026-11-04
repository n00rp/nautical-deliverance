"""Fail unless line AND branch coverage are each at least 90 % (D-035).

Usage: python tools/check_coverage.py coverage.json   (from `coverage json`)
"""

import json
import sys
from pathlib import Path

THRESHOLD = 90.0


def check(totals: dict[str, float]) -> list[str]:
    """Return one message per metric below the threshold."""
    lines = 100.0 * totals["covered_lines"] / max(totals["num_statements"], 1)
    branches = 100.0 * totals["covered_branches"] / max(totals["num_branches"], 1)
    return [
        f"{name} coverage {value:.2f} % is below {THRESHOLD:.0f} %"
        for name, value in (("line", lines), ("branch", branches))
        if value < THRESHOLD
    ]


def main(argv: list[str]) -> int:
    """Read a coverage JSON report and print failures."""
    totals = json.loads(Path(argv[1]).read_text(encoding="utf-8"))["totals"]
    problems = check(totals)
    print("\n".join(problems) or "line and branch coverage both >= 90 %")  # noqa: T201
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
