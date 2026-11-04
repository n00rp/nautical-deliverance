"""Tests for the line/branch coverage gate (S0-R07)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECK = Path(__file__).parent / "check_coverage.py"


def _run(tmp_path: Path, lines: tuple[int, int], branches: tuple[int, int]) -> int:
    report = tmp_path / "coverage.json"
    totals = {
        "covered_lines": lines[0],
        "num_statements": lines[1],
        "covered_branches": branches[0],
        "num_branches": branches[1],
    }
    report.write_text(json.dumps({"totals": totals}), encoding="utf-8")
    return subprocess.run(  # noqa: S603
        [sys.executable, str(CHECK), str(report)], capture_output=True, check=False
    ).returncode


@pytest.mark.req("S0-R07")
def test_passes_when_both_at_threshold(tmp_path: Path) -> None:
    assert _run(tmp_path, (90, 100), (9, 10)) == 0


@pytest.mark.req("S0-R07")
def test_fails_when_only_branches_are_low(tmp_path: Path) -> None:
    assert _run(tmp_path, (100, 100), (8, 10)) == 1


@pytest.mark.req("S0-R07")
def test_fails_when_only_lines_are_low(tmp_path: Path) -> None:
    assert _run(tmp_path, (89, 100), (10, 10)) == 1
