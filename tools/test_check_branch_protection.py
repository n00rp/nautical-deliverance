"""Tests for the repository merge-settings check (S0-R12), using a fake `gh` on PATH."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "check_branch_protection.sh"
GOOD = {"allow_squash_merge": True, "allow_merge_commit": False, "allow_rebase_merge": False}

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


JQ = (
    "[.allow_squash_merge, .allow_merge_commit, .allow_rebase_merge]"
    ' | map(if . == null then "missing" else tostring end) | @tsv'
)
FAKE_GH_PY = r"""
import json, sys
reply = open(sys.argv[1]).read()
if "--jq" not in sys.argv:
    print(reply)
    sys.exit(0)
# The expression must be exactly the one under test; the fake evaluates only that one.
assert sys.argv[sys.argv.index("--jq") + 1] == JQ, "script uses a different jq expression"
try:
    data = json.loads(reply)
except ValueError:
    print(reply, file=sys.stderr)
    sys.exit(1)
keys = ["allow_squash_merge", "allow_merge_commit", "allow_rebase_merge"]
# Same result as the real `[...] | @tsv`: top-level keys only, null/missing -> 'missing'.
cell = lambda v: "missing" if v is None else str(v).lower()
print("\t".join(cell(data.get(k)) for k in keys))
"""


def _run(tmp_path: Path, reply: str) -> subprocess.CompletedProcess[str]:
    """Run the script with a fake `gh` that honours `--jq`; non-JSON replies make it fail."""
    (tmp_path / "reply.json").write_text(reply)
    (tmp_path / "fake_gh.py").write_text(f"JQ = {JQ!r}" + chr(10) + FAKE_GH_PY)
    shim = tmp_path / "gh"
    fake = f"{tmp_path}/fake_gh.py"
    line = f'exec "{sys.executable}" "{fake}" "{tmp_path}/reply.json" "$@"'
    shim.write_text(chr(10).join(["#!/usr/bin/env bash", line, ""]))
    shim.chmod(0o755)
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
    result = _run(tmp_path, "gh: Not Found (HTTP 404)")
    assert result.returncode not in (0, 1)
    assert "cannot read" in result.stderr


@pytest.mark.req("S0-R12")
def test_nested_duplicate_keys_are_ignored(tmp_path: Path) -> None:
    flipped = {k: not v for k, v in GOOD.items()}
    reply = {
        **GOOD,
        "parent": flipped,
        "template_repository": flipped,
        "description": '"allow_squash_merge": false',
    }
    assert _run(tmp_path, json.dumps(reply)).returncode == 0


@pytest.mark.req("S0-R12")
def test_missing_or_null_key_is_a_mismatch(tmp_path: Path) -> None:
    reply = {"allow_squash_merge": True, "allow_merge_commit": None, "parent": GOOD}
    result = _run(tmp_path, json.dumps(reply))
    assert result.returncode == 1
    assert "allow_merge_commit" in result.stderr
    assert "allow_rebase_merge" in result.stderr


@pytest.mark.req("S0-R12")
def test_null_middle_key_does_not_shift_positions(tmp_path: Path) -> None:
    reply = {"allow_squash_merge": True, "allow_merge_commit": None, "allow_rebase_merge": False}
    result = _run(tmp_path, json.dumps(reply))
    assert result.returncode == 1
    assert "allow_merge_commit is missing" in result.stderr
    assert "allow_rebase_merge" not in result.stderr
