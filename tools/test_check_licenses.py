"""Tests for the dependency license checker (S0-R10)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECK = Path(__file__).parent / "check_licenses.py"


def _run(
    tmp_path: Path, pip: list[dict[str, str]], pnpm: dict[str, list[dict[str, object]]], *extra: str
) -> subprocess.CompletedProcess[str]:
    (tmp_path / "pip.json").write_text(json.dumps(pip), encoding="utf-8")
    (tmp_path / "pnpm.json").write_text(json.dumps(pnpm), encoding="utf-8")
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(CHECK),
            "--pip",
            str(tmp_path / "pip.json"),
            "--pnpm",
            str(tmp_path / "pnpm.json"),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _pip(name: str, lic: str) -> dict[str, str]:
    return {"Name": name, "Version": "1.0", "License": lic}


def _pnpm(name: str) -> dict[str, object]:
    return {"name": name, "versions": ["1.0.0"]}


@pytest.mark.req("S0-R10")
def test_allows_listed_licenses(tmp_path: Path) -> None:
    pip = [
        _pip(n, lic)
        for n, lic in [
            ("a", "MIT"),
            ("b", "BSD-3-Clause"),
            ("c", "Apache-2.0"),
            ("d", "MIT OR Apache-2.0"),
            ("e", "MIT AND BSD-2-Clause"),
            ("f", "LGPL-3.0-or-later"),
            ("g", "MPL-2.0"),
            ("h", "ISC"),
            ("i", "PSF-2.0"),
            ("j", "GPL-3.0-only OR MIT"),
        ]
    ]
    result = _run(tmp_path, pip, {"MIT": [_pnpm("x")], "ISC": [_pnpm("y")]})
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.req("S0-R10")
def test_rejects_gpl(tmp_path: Path) -> None:
    result = _run(tmp_path, [_pip("badpkg", "GPL-3.0-only")], {})
    assert result.returncode == 1
    assert "badpkg" in result.stdout + result.stderr


@pytest.mark.req("S0-R10")
def test_rejects_gpl_in_pnpm(tmp_path: Path) -> None:
    result = _run(tmp_path, [], {"GPL-3.0-only": [_pnpm("badjs")]})
    assert result.returncode == 1
    assert "badjs" in result.stdout + result.stderr


@pytest.mark.req("S0-R10")
@pytest.mark.parametrize("lic", ["UNKNOWN", "Proprietary stuff", "", "MIT AND GPL-2.0-only"])
def test_rejects_unknown_license_string(tmp_path: Path, lic: str) -> None:
    result = _run(tmp_path, [_pip("weird", lic)], {})
    assert result.returncode == 1
    assert "weird" in result.stdout + result.stderr


@pytest.mark.req("S0-R10")
def test_approved_file_exempts_named_package(tmp_path: Path) -> None:
    approved = tmp_path / "approved.txt"
    approved.write_text("# owner-approved\nweird\n", encoding="utf-8")
    result = _run(tmp_path, [_pip("weird", "UNKNOWN")], {}, "--approved", str(approved))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.req("S0-R10")
def test_allows_trove_classifier_names(tmp_path: Path) -> None:
    pip = [_pip("a", "MIT License"), _pip("b", "Apache Software License"), _pip("c", "BSD License")]
    assert _run(tmp_path, pip, {}).returncode == 0
