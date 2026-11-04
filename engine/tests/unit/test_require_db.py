"""CI must never skip DB tests silently (ND_REQUIRE_DB)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).parents[2]


def _run_db_tests(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ND_")} | extra_env
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/db/test_rls.py", "-q", "-p", "no:cacheprovider"],
        cwd=ENGINE, env=env, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.mark.req("S0-R07")
def test_db_tests_skip_without_dsn_by_default() -> None:
    """Local runs without a database skip."""
    out = _run_db_tests({}).stdout
    assert "skipped" in out
    assert "failed" not in out


@pytest.mark.req("S0-R07")
def test_require_db_fails_instead_of_skipping() -> None:
    """With ND_REQUIRE_DB=1 a missing database fails."""
    result = _run_db_tests({"ND_REQUIRE_DB": "1"})
    assert result.returncode != 0
    assert "error" in result.stdout
    assert "skipped" not in result.stdout
