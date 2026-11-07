"""infra/deploy/deploy.sh guards (B6-R07, I5): on main, not older than the deployed commit.

Runs the real script in a throw-away clone with a fake `docker`, so no Docker is needed.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BASH = shutil.which("bash")
USAGE_ERROR = 2
pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")


def _git(cwd: Path, *args: str) -> str:
    who = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t"}
    env = {**os.environ, **who, "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    done = subprocess.run(  # noqa: S603 - fixed arguments in a temp repository
        ["git", *args],  # noqa: S607
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


@pytest.fixture
def server(tmp_path: Path) -> dict[str, object]:
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    (origin / "infra" / "deploy").mkdir(parents=True)
    shutil.copy(ROOT / "infra" / "deploy" / "deploy.sh", origin / "infra" / "deploy" / "deploy.sh")
    shas = []
    for n in range(3):
        (origin / "f.txt").write_text(str(n), encoding="utf-8")
        _git(origin, "add", "-A")
        _git(origin, "commit", "-q", "-m", f"c{n}")
        shas.append(_git(origin, "rev-parse", "HEAD"))
    _git(origin, "checkout", "-q", "-b", "feature", shas[0])
    (origin / "g.txt").write_text("x", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "side")
    side = _git(origin, "rev-parse", "HEAD")
    _git(origin, "checkout", "-q", "main")
    clone = tmp_path / "nd"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    (clone / "infra" / ".env.prod").write_text("", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text('#!/bin/sh\necho "$@" >> "$FAKE_DOCKER_LOG"\n', encoding="utf-8")
    fake.chmod(0o755)
    return {
        "clone": clone,
        "shas": shas,
        "side": side,
        "state": tmp_path / "DEPLOYED_SHA",
        "first": tmp_path / "nd-state" / "FIRST_DEPLOYED",
        "bin": bin_dir,
        "log": tmp_path / "docker.log",
    }


def _deploy(server: dict[str, object], *args: str) -> subprocess.CompletedProcess[str]:
    clone = server["clone"]
    assert isinstance(clone, Path)
    env = {
        **os.environ,
        "PATH": f"{server['bin']}{os.pathsep}{os.environ['PATH']}",
        "ND_DEPLOYED_SHA_FILE": str(server["state"]),
        "ND_FIRST_DEPLOYED_FILE": str(server["first"]),
        "FAKE_DOCKER_LOG": str(server["log"]),
    }
    assert BASH is not None
    return subprocess.run(  # noqa: S603 - the script under test, in a temp clone
        [BASH, "infra/deploy/deploy.sh", *args],
        cwd=clone,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.req("B6-R07")
def test_deploys_a_commit_on_main_and_records_it(server: dict[str, object]) -> None:
    shas = server["shas"]
    assert isinstance(shas, list)
    result = _deploy(server, shas[1])
    assert result.returncode == 0, result.stderr
    assert Path(str(server["state"])).read_text(encoding="utf-8").strip() == shas[1]
    assert "up -d --remove-orphans --wait" in Path(str(server["log"])).read_text(encoding="utf-8")


@pytest.mark.req("B6-R07")
def test_refuses_a_commit_that_is_not_on_main(server: dict[str, object]) -> None:
    result = _deploy(server, str(server["side"]))
    assert result.returncode == 1
    assert "not an ancestor of origin/main" in result.stderr
    assert not Path(str(server["state"])).exists()
    assert not Path(str(server["log"])).exists(), "nothing may be built or started"


@pytest.mark.req("B6-R07")
def test_refuses_an_older_commit_unless_rollback_is_allowed(server: dict[str, object]) -> None:
    shas = server["shas"]
    assert isinstance(shas, list)
    assert _deploy(server, shas[2]).returncode == 0
    older = _deploy(server, shas[0])
    assert older.returncode == 1
    assert "--allow-rollback" in older.stderr
    assert Path(str(server["state"])).read_text(encoding="utf-8").strip() == shas[2]
    again = _deploy(server, shas[2])  # the same commit again is a plain redeploy
    assert again.returncode == 0, again.stderr
    back = _deploy(server, "--allow-rollback", shas[0])
    assert back.returncode == 0, back.stderr
    assert Path(str(server["state"])).read_text(encoding="utf-8").strip() == shas[0]
    forward = _deploy(server, shas[1])  # newer than the deployed one: no flag needed
    assert forward.returncode == 0, forward.stderr


@pytest.mark.req("B6-R07")
def test_rejects_a_malformed_sha(server: dict[str, object]) -> None:
    assert _deploy(server, "main").returncode == USAGE_ERROR


@pytest.mark.req("B6-R07")
def test_first_deployed_is_written_once_and_never_overwritten(server: dict[str, object]) -> None:
    shas = server["shas"]
    assert isinstance(shas, list)
    first = Path(str(server["first"]))  # its directory does not exist yet: deploy.sh creates it
    assert _deploy(server, shas[0]).returncode == 0
    stamp = first.read_text(encoding="utf-8")
    assert stamp.strip().endswith("Z")
    first.write_text("keep", encoding="utf-8")
    assert _deploy(server, shas[1]).returncode == 0
    assert first.read_text(encoding="utf-8") == "keep"
