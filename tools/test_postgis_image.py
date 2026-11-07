"""The database image is our own multi-arch PostGIS build, pinned by digest (B6-R02)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "infra" / "postgis" / "Dockerfile"
COMPOSE = ROOT / "infra" / "docker-compose.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
HEAVY = ROOT / ".github" / "workflows" / "heavy.yml"


@pytest.mark.req("B6-R02")
def test_dockerfile_from_is_digest_pinned_postgres_17() -> None:
    from_lines = re.findall(r"^FROM (\S+)", DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert len(from_lines) == 1
    assert re.fullmatch(r"postgres:17[\w.-]*@sha256:[0-9a-f]{64}", from_lines[0])


@pytest.mark.req("B6-R02")
def test_dockerfile_pins_postgis_package_exactly() -> None:
    assert re.search(r"postgresql-17-postgis-3=\S+", DOCKERFILE.read_text(encoding="utf-8"))


@pytest.mark.req("B6-R02")
def test_dockerfile_pins_scripts_and_geo_libraries_and_blocks_pgdg_geo() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    for pkg in (
        "postgresql-17-postgis-3-scripts",
        "libgeos-c1t64",
        "libproj25",
        "libgdal36",
        "gdal-data",
        "gdal-plugins",
        "libsfcgal2",
    ):
        assert re.search(rf"{re.escape(pkg)}=[^\s\\]+", text), pkg
    assert "Pin-Priority: -1" in text


@pytest.mark.req("B6-R02")
def test_gosu_is_replaced_by_setpriv_wrapper_in_its_own_layer() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "rm -rf /var/lib/apt/lists/* /usr/local/bin/gosu" in text
    assert re.search(r"^RUN printf .*setpriv", text, re.MULTILINE | re.DOTALL)


@pytest.mark.req("B6-R02")
def test_multiarch_job_lives_in_the_heavy_workflow_with_pinned_emulation() -> None:
    heavy = HEAVY.read_text(encoding="utf-8")
    job = heavy.split("\n  multiarch:\n", 1)[1].split("\n  # req:", 1)[0]
    assert "context: [infra/postgis, infra/backup, engine, web]" in job
    assert "--platform linux/amd64,linux/arm64" in job
    assert "--push" not in job.split("docker buildx build", 1)[1]
    # I9: the privileged binfmt image and BuildKit are pinned by digest, never :latest.
    assert re.search(r"image: tonistiigi/binfmt@sha256:[0-9a-f]{64}", job)
    assert re.search(r"image=moby/buildkit@sha256:[0-9a-f]{64}", job)
    assert "multiarch" not in CI.read_text(encoding="utf-8")


@pytest.mark.req("B6-R02")
def test_web_build_stage_runs_on_the_build_host() -> None:
    dockerfile = (ROOT / "web" / "Dockerfile").read_text(encoding="utf-8")
    pattern = r"^FROM --platform=\$BUILDPLATFORM node:\S+ AS build$"
    assert re.search(pattern, dockerfile, re.MULTILINE)


@pytest.mark.req("B6-R02")
def test_heavy_workflow_triggers_and_duration_note() -> None:
    heavy = HEAVY.read_text(encoding="utf-8")
    head = heavy.split("\njobs:\n", 1)[0]
    for trigger in ("schedule:", "workflow_dispatch:", "push:", "pull_request:"):
        assert trigger in head
    paths = ("infra/**", "**/Dockerfile", "web/e2e/**", "tools/*backup*", "tools/*smoke*")
    for path in (*paths, "tools/pilot_*"):
        assert head.count(f'"{path}"') == len(("push", "pull_request")), path
    jobs = {"e2e", "multiarch", "prod-overlay", "pilot-user", "backup-restore"}
    ci = CI.read_text(encoding="utf-8")
    for name in jobs:
        assert f"\n  {name}:\n" in heavy, name
        assert f"\n  {name}:\n" not in ci, name
    duration = heavy.split("  heavy-duration:", 1)[1]
    assert all(name in duration.split("steps:", 1)[0] for name in jobs)
    assert "2700" in duration
    assert "needs: [engine, web, visual, traceability, security, smoke, lint-scripts, readme]" in ci


@pytest.mark.req("B6-R02")
def test_compose_db_uses_the_own_image() -> None:
    db = COMPOSE.read_text(encoding="utf-8").split("\n  db:\n", 1)[1].split("\n\n", 1)[0]
    assert "image: nautical-deliverance/postgis:${ND_IMAGE_TAG:-dev}" in db
    assert "context: ./postgis" in db


@pytest.mark.req("B6-R02")
def test_no_stock_postgis_image_left() -> None:
    assert "postgis/postgis" not in COMPOSE.read_text(encoding="utf-8")
    assert "postgis/postgis" not in CI.read_text(encoding="utf-8")
