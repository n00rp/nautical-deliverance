"""Architecture layer contract tests."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2]
PKG = "src/nautical_deliverance"

DOMAIN_PURE = "domain is pure"
NO_API = "persistence does not import api"
CONTRACTS_FREE = "contracts and reference stay framework-free"


def _lint(root: Path) -> tuple[int, str]:
    result = subprocess.run(  # noqa: S603
        [str(Path(sys.executable).parent / "lint-imports")],
        cwd=root,
        check=False,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONIOENCODING": "utf-8"},
    )
    return result.returncode, result.stdout + result.stderr


def _copy_tree(tmp_path: Path) -> Path:
    root = tmp_path / "engine"
    root.mkdir()
    shutil.copy(ENGINE / "pyproject.toml", root)
    shutil.copytree(ENGINE / "src", root / "src")
    return root


@pytest.mark.req("S0-R05")
@pytest.mark.req("S0b-R11")
def test_layer_contracts_pass_on_clean_tree(tmp_path: Path) -> None:
    """The unmodified tree satisfies every contract."""
    code, output = _lint(_copy_tree(tmp_path))

    assert code == 0, output
    assert "Contracts: 3 kept, 0 broken." in output


@pytest.mark.req("S0-R05")
@pytest.mark.parametrize(
    ("layer", "forbidden", "contract"),
    [
        ("domain", "fastapi", DOMAIN_PURE),
        ("domain", "sqlalchemy", DOMAIN_PURE),
        ("domain", "nautical_deliverance.api", DOMAIN_PURE),
        ("domain", "nautical_deliverance.persistence", DOMAIN_PURE),
        ("persistence", "nautical_deliverance.api", NO_API),
        ("domain/contracts", "pydantic", CONTRACTS_FREE),
    ],
)
def test_layer_contracts_reject_violation(
    tmp_path: Path, layer: str, forbidden: str, contract: str
) -> None:
    """Each forbidden import breaks exactly its contract (exit 1, not a crash)."""
    root = _copy_tree(tmp_path)
    with (root / PKG / layer / "__init__.py").open("a") as f:
        f.write(f"\nimport {forbidden}\n")

    code, output = _lint(root)

    assert code == 1, output
    assert f"{contract} BROKEN" in output, output
    assert "1 broken" in output, output
