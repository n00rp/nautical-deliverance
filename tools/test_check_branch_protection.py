"""Tests for the repository merge-settings check (S0-R12), using a fake `gh` on PATH."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "check_branch_protection.sh"
GOOD = {"allow_squash_merge": True, "allow_merge_commit": False, "allow_rebase_merge": False}

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _run(tmp_path: Path, reply: str, gh_exit: int = 0) -> subprocess.CompletedProcess[str]:
    fake = tmp_path / "gh"
    fake.write_text(f"#!/usr/bin/env bash\ncat <<'JSON'\n{reply}\nJSON\nexit {gh_exit}\n")
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.mark.req("S0-R12")
def test_matching_settings_pass(tmp_path: Path) -> None:
    result = _run(tmp_path, json.dumps(GOOD))
    assert result.returncode == 0, result.stderr


@pytest.mark.req("S0-R12")
def test_every_mismatch_is_listed(tmp_path: Path) -> None:
    bad = {"allow_squash_merge": False, "allow_merge_commit": True, "allow_rebase_merge": True}
    result = _run(tmp_path, json.dumps(bad))
    assert result.returncode == 1
    for key in bad:
        assert key in result.stderr


@pytest.mark.req("S0-R12")
def test_unreachable_repo_fails_clearly(tmp_path: Path) -> None:
    result = _run(tmp_path, "gh: Not Found (HTTP 404)", gh_exit=1)
    assert result.returncode not in (0, 1)
    assert "cannot read" in result.stderr
