"""Tests for the requirement traceability checker (S0-R09)."""

import subprocess
import sys
from pathlib import Path

import pytest

TRACE = Path(__file__).parent / "trace.py"
SPEC = "docs/superpowers/specs/s.md"
# Built indirectly so this file's own source does not look like a reference to the scanner.
MARK = "req" + '("{}")'


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _repo(root: Path, ids: list[str], files: dict[str, str]) -> None:
    rows = "".join(f"| {i} | name | text |\n" for i in ids)
    _write(root, SPEC, "| ID | Name | Text |\n|---|---|---|\n" + rows)
    for rel, text in files.items():
        _write(root, rel, text)


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(TRACE), "--root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _test_file(*ids: str) -> str:
    return "".join(f"def test_{n}():\n    {MARK.format(i)}\n" for n, i in enumerate(ids))


@pytest.mark.req("S0-R09")
def test_passes_when_every_requirement_has_a_test(tmp_path: Path) -> None:
    _repo(tmp_path, ["S0-R01"], {"engine/tests/x.py": _test_file("S0-R01")})
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    matrix = (tmp_path / "docs/traceability.md").read_text(encoding="utf-8")
    assert "S0-R01 | engine/tests/x.py" in matrix


@pytest.mark.req("S0-R09")
def test_fails_on_requirement_without_test(tmp_path: Path) -> None:
    _repo(tmp_path, ["S0-R01", "S0-R02"], {"engine/tests/x.py": _test_file("S0-R01")})
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "S0-R02: no test" in result.stderr


@pytest.mark.req("S0-R09")
def test_fails_on_unknown_reference(tmp_path: Path) -> None:
    _repo(tmp_path, ["S0-R01"], {"engine/tests/x.py": _test_file("S0-R01", "S0-R99")})
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "S0-R99: unknown requirement" in result.stderr


@pytest.mark.req("S0-R09")
def test_check_fails_when_committed_matrix_is_stale(tmp_path: Path) -> None:
    _repo(tmp_path, ["S0-R01"], {"engine/tests/x.py": _test_file("S0-R01")})
    assert _run(tmp_path).returncode == 0
    assert _run(tmp_path, "--check").returncode == 0
    _write(tmp_path, "docs/traceability.md", "stale\n")
    result = _run(tmp_path, "--check")
    assert result.returncode == 1
    assert "docs/traceability.md is out of date" in result.stderr


@pytest.mark.req("S0-R09")
def test_workflow_comment_with_several_ids(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        ["S0-R06", "S0-R07", "S0-R15"],
        {".github/workflows/ci.yml": "# req: S0-R06 S0-R07 S0-R15\non: push\n"},
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    matrix = (tmp_path / "docs/traceability.md").read_text(encoding="utf-8")
    assert "S0-R07 | .github/workflows/ci.yml" in matrix


@pytest.mark.req("S0-R09")
def test_web_test_names_reference_ids(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        ["S0-R04"],
        {"web/src/a.test.tsx": "it('[S0-R04] renders', () => {});\n"},
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "S0-R04 | web/src/a.test.tsx" in (tmp_path / "docs/traceability.md").read_text(
        encoding="utf-8"
    )
