"""infra/backup/check_fresh.sh: bucket check, bounded first-backup grace, stale marker (B6-R06/R07).

Runs the real script with a fake `rclone` on PATH, so no Docker is needed.
"""

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")
STAMP = "%Y-%m-%d %H:%M:%S"
# lsd = bucket check (rc 3 = bucket missing); lsf = marker listing (rc 3 = nd/ prefix missing).
FAKE_RCLONE = """#!/bin/sh
# the real command line starts with global flags: pick the subcommand
for a in "$@"; do case "$a" in lsd | lsf) cmd=$a ;; esac; done
case "$cmd" in
  lsd) [ "$FAKE_BUCKET" = 1 ] || exit 3 ;;
  lsf) [ -n "$FAKE_MARKER" ] || exit 3; echo "$FAKE_MARKER;nd/x.ok" ;;
esac
"""


def _ago(hours: float) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).strftime(STAMP)


def _check(
    tmp_path: Path,
    *,
    bucket: bool = True,
    marker_h: float | None = None,
    first_h: float | None = None,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "rclone"
    fake.write_text(FAKE_RCLONE, encoding="utf-8")
    fake.chmod(0o755)
    recipients = tmp_path / "recipients.txt"
    recipients.write_text("age1real\n", encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "ND_AGE_RECIPIENTS": str(recipients),
        "FAKE_BUCKET": "1" if bucket else "0",
        "FAKE_MARKER": _ago(marker_h) if marker_h is not None else "",
        "ND_FIRST_DEPLOYED": _ago(first_h) if first_h is not None else "",
    }
    for v in ("BUCKET", "S3_ENDPOINT", "S3_REGION", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        env[f"ND_BACKUP_{v}"] = "x"
    env.update(PGHOST="x", PGUSER="x", PGPASSWORD="x")
    assert BASH is not None
    return subprocess.run(  # noqa: S603 - the script under test
        [BASH, str(ROOT / "infra" / "backup" / "check_fresh.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.req("B6-R06")
def test_missing_bucket_fails_even_in_the_grace_period(tmp_path: Path) -> None:
    done = _check(tmp_path, bucket=False, first_h=1)
    assert done.returncode != 0
    assert "bucket" in done.stderr


@pytest.mark.req("B6-R06")
def test_empty_bucket_passes_inside_the_grace_period(tmp_path: Path) -> None:
    assert _check(tmp_path, first_h=2).returncode == 0


@pytest.mark.req("B6-R06")
def test_empty_bucket_fails_after_the_grace_period(tmp_path: Path) -> None:
    done = _check(tmp_path, first_h=30)
    assert done.returncode != 0
    assert "no backup" in done.stderr


@pytest.mark.req("B6-R06")
def test_empty_bucket_fails_without_first_deployed(tmp_path: Path) -> None:
    done = _check(tmp_path)
    assert done.returncode != 0
    assert "FIRST_DEPLOYED" in done.stderr


@pytest.mark.req("B6-R06")
def test_stale_marker_fails_even_inside_the_grace_period(tmp_path: Path) -> None:
    assert _check(tmp_path, marker_h=30, first_h=1).returncode != 0


@pytest.mark.req("B6-R06")
def test_fresh_marker_passes_without_first_deployed(tmp_path: Path) -> None:
    assert _check(tmp_path, marker_h=3).returncode == 0
