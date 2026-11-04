"""Architecture layer contract tests."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2]


def _lint(root: Path) -> int:
    return subprocess.run(  # noqa: S603
        [str(Path(sys.executable).parent / "lint-imports")],
        cwd=root,
        check=False,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
    ).returncode


@pytest.mark.req("S0-R05")
def test_layer_contracts_reject_violation(tmp_path: Path) -> None:
    """Contracts pass on the real tree and fail when domain imports fastapi."""
    root = tmp_path / "engine"
    root.mkdir()
    shutil.copy(ENGINE / "pyproject.toml", root)
    shutil.copytree(ENGINE / "src", root / "src")

    assert _lint(root) == 0

    with (root / "src/nautical_deliverance/domain/__init__.py").open("a") as f:
        f.write("\nimport fastapi\n")

    assert _lint(root) != 0
