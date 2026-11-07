"""Deploy workflow (B6-R07), runbook (B6-R09) and user guide (B6-R10): static checks."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
RUNBOOK = ROOT / "docs" / "deploy" / "oracle-runbook.md"
GUIDE = ROOT / "docs" / "user-guide.md"
README = ROOT / "README.md"
INFRA = ROOT / "infra"
# Provided by GitHub itself, not by the owner.
BUILTIN_SECRETS = {"GITHUB_TOKEN"}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _runbook_words() -> str:
    return _text(RUNBOOK)


def _names(pattern: str, text: str) -> set[str]:
    return set(re.findall(pattern, text))


@pytest.mark.req("B6-R07")
def test_workflow_runs_only_after_green_ci_push_on_main() -> None:
    wf = _text(WORKFLOW)
    assert re.search(r"workflow_run:\s*\n\s*workflows:\s*\[CI\]", wf)
    assert re.search(r"types:\s*\[completed\]", wf)
    assert re.search(r"branches:\s*\[main\]", wf)
    # Review Focus #1: both conditions, so neither a failed CI nor a PR run can deploy.
    assert "github.event.workflow_run.conclusion == 'success'" in wf
    assert "github.event.workflow_run.event == 'push'" in wf
    assert "workflow_dispatch" in wf
    assert "head_sha" in wf


@pytest.mark.req("B6-R07")
def test_workflow_is_serialised_and_strict_about_hosts() -> None:
    wf = _text(WORKFLOW)
    assert re.search(r"concurrency:\s*\n\s*group:\s*deploy-pilot", wf)
    assert "cancel-in-progress: false" in wf
    assert "StrictHostKeyChecking=yes" in wf
    assert "StrictHostKeyChecking=no" not in wf
    assert "ND_DEPLOY_KNOWN_HOSTS" in wf
    assert "UserKnownHostsFile" not in wf or "/dev/null" not in wf


@pytest.mark.req("B6-R07")
def test_nothing_ever_deletes_volumes() -> None:
    for path in (WORKFLOW, INFRA / "deploy" / "deploy.sh", INFRA / "deploy" / "cloud-init.yaml"):
        text = _text(path)
        assert not re.search(r"\bdown\b[^\n]*(-v\b|--volumes)", text), path
        assert "volume rm" not in text, path


@pytest.mark.req("B6-R07")
def test_deploy_script_pins_the_sha_and_builds_natively() -> None:
    sh = _text(INFRA / "deploy" / "deploy.sh")
    assert "git fetch" in sh
    assert "git checkout --detach" in sh
    assert "docker-compose.prod.yml" in sh
    assert "--env-file infra/.env.prod" in sh or "--env-file" in sh
    assert " build" in sh
    assert "up -d --remove-orphans" in sh
    assert re.search(r"\^\[0-9a-f\]\{40\}\$", sh), "the sha argument must be validated"


@pytest.mark.req("B6-R07")
def test_backup_check_runs_on_every_deploy_and_tolerates_only_a_missing_first_backup() -> None:
    wf = _text(WORKFLOW)
    assert "first_deploy" not in wf
    assert "--check-backup" in wf
    assert (INFRA / "backup" / "check_fresh.sh").is_file()
    assert "26" in _text(INFRA / "backup" / "check_fresh.sh")
    script = _text(INFRA / "backup" / "check_fresh.sh")
    assert "no backup .ok marker" in script  # M-2: warns and passes before the first backup
    assert 'die "newest backup is' in script  # but a stale newest marker still fails


@pytest.mark.req("B6-R07")
def test_deploy_gate_covers_only_the_automatic_path_and_dispatch_needs_main() -> None:
    wf = _text(WORKFLOW)
    condition = re.search(r"\n    if: >-\n((?:      .*\n)+)", wf)
    assert condition, "the deploy job needs an if"
    manual, automatic = " ".join(condition.group(1).split()).split(" || ", 1)
    assert "workflow_dispatch" in manual
    assert "github.ref == 'refs/heads/main'" in manual
    # I1: the first manual deploy happens before the switch is turned on.
    assert "ND_DEPLOY_ENABLED" not in manual
    assert "vars.ND_DEPLOY_ENABLED == 'true'" in automatic
    assert "workflow_run.conclusion == 'success'" in automatic
    # I5: a manual deploy needs a green push CI run for that exact commit.
    assert re.search(r"actions:\s*read", wf)
    assert "head_sha=$SHA&event=push&status=success" in wf
    assert "allow_rollback" in wf
    assert "--allow-rollback" in wf


@pytest.mark.req("B6-R09")
def test_every_github_secret_is_in_the_runbook() -> None:
    secrets = _names(r"secrets\.([A-Z0-9_]+)", _text(WORKFLOW)) - BUILTIN_SECRETS
    assert {"ND_DEPLOY_SSH_KEY", "ND_DEPLOY_KNOWN_HOSTS", "ND_DEPLOY_HOST"} <= secrets
    missing = sorted(s for s in secrets if s not in _runbook_words())
    assert not missing, f"secrets missing from the runbook: {missing}"
    variables = _names(r"vars\.([A-Z0-9_]+)", _text(WORKFLOW))
    assert not [v for v in variables if v not in _runbook_words()]


@pytest.mark.req("B6-R09")
def test_every_env_variable_is_in_the_runbook() -> None:
    compose = _text(INFRA / "docker-compose.prod.yml")
    names = _names(r"\$\{([A-Z][A-Z0-9_]*)", compose)
    names |= _names(r"^([A-Z][A-Z0-9_]*)=", _text(INFRA / ".env.prod.example"))
    assert len(names) >= 10  # noqa: PLR2004 - guards against a broken regex
    missing = sorted(n for n in names if n not in _runbook_words())
    assert not missing, f"variables missing from the runbook: {missing}"


RUNBOOK_TOPICS = {
    "card verification": "card",
    "A1.Flex 2 OCPU / 12 GB": "2 OCPU",
    "region choice": "Region",
    "security list": "security list",
    "DuckDNS update cron": "duckdns.org/update",
    "bucket lifecycle rule": "14-day",
    "customer secret key": "customer secret key",
    "age keygen": "age-keygen",
    "private key offline": "offline",
    "age-recipients.txt replaced": "age-recipients.txt",
    "test-decrypt of the first backup": "test-decrypt",
    "restore drill": "Restore drill",
    "restore log template": "Drill log",
    "pilot_user.py": "pilot_user.py",
    "named Keycloak admin": "bootstrap admin",
    "fresh volume on first deploy": "empty volume",
    "DB password rotation": "ALTER ROLE",
    "SSH tunnel": "ssh -L 8081:127.0.0.1:8081",
    "docker.service enabled": "systemctl enable docker",
    "deploy key": "deploy key",
    "ARM iptables": "iptables",
    "first Let's Encrypt is the h1 test": "protocols h1",
    "permanent password before E2E": "permanent password",
    "backup staleness": "check_fresh.sh",
    "teardown and rebuild": "Tear down",
}


@pytest.mark.req("B6-R09")
@pytest.mark.parametrize("topic", sorted(RUNBOOK_TOPICS))
def test_runbook_covers(topic: str) -> None:
    assert RUNBOOK_TOPICS[topic].lower() in _runbook_words().lower()


@pytest.mark.req("B6-R09")
def test_cloud_init_is_key_only_and_opens_three_ports() -> None:
    ci = _text(INFRA / "deploy" / "cloud-init.yaml")
    assert ci.startswith("#cloud-config")
    assert "PasswordAuthentication no" in ci
    assert "download.docker.com" in ci
    for port in ("22", "80", "443"):
        assert f"--dport {port} " in ci
    assert not re.search(r"--dport (?!22|80|443)\d+", ci)
    assert "duckdns.org/update" in ci
    assert "docker" in ci
    assert "deploy" in ci
    # M-1: the saved iptables rules must be taken before Docker adds its chains.
    runcmd = ci.split("runcmd:", 1)[1]
    assert runcmd.index("nd-open-ports") < runcmd.index("nd-install-docker")
    assert "/srv/nd" in ci  # where deploy.sh records the deployed commit


@pytest.mark.req("B6-R09")
def test_runbook_secrets_are_url_safe_and_commands_use_the_right_user() -> None:
    book = _runbook_words()
    assert "-base64" not in book  # C2: '/' and '+' in a password break database URLs
    assert "openssl rand -hex 24" in book
    assert "MSYS_NO_PATHCONV=1" in book  # I4: Git Bash rewrites container paths otherwise
    # I2: `deploy` has no sudo; root steps run as ubuntu; deploy is reached with sudo -iu deploy.
    assert not re.search(r"^\s*deploy\$ sudo ", book, re.MULTILINE)
    assert "sudo -iu deploy" in book
    assert "--allow-rollback" in book
    assert "allow_rollback" in book
    assert "--force" in book  # I3: restoring onto a server that already holds data


GUIDE_HEADINGS = [
    "## Demo data notice",
    "## Sign in",
    "## Roles",
    "## The purchase flow",
    "## Confidentiality",
]
# Exact UI labels (web/e2e/flow.spec.ts drives the same ones).
GUIDE_LABELS = [
    "Sign in",
    "New inquiry",
    "Create inquiry",
    "Select suppliers",
    "Mark sent",
    "Confirm sent",
    "Enter offer",
    "Save offer",
    "Compare offers",
    "Select winner",
    "Confirm selection",
    "Create nomination",
    "Inquiries by status",
]


@pytest.mark.req("B6-R10")
def test_user_guide_has_headings_labels_and_a_readme_link() -> None:
    guide = _text(GUIDE)
    lines = guide.splitlines()
    for heading in GUIDE_HEADINGS:
        assert heading in lines, heading
    for label in GUIDE_LABELS:
        assert f"**{label}**" in guide, label
    readme = _text(README)
    assert "docs/user-guide.md" in readme
    assert "docs/deploy/oracle-runbook.md" in readme
