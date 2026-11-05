"""S0b-R11 as an allow-list: contracts and reference import only stdlib, NumPy, GeographicLib.

The import-linter contract (tests/unit/test_layers.py) forbids a list of known frameworks; this
test is the converse and catches any new third-party import. Imports anywhere in a file count
(including `if TYPE_CHECKING` blocks and function bodies), as do `__import__` and `importlib`.
"""

import ast
import sys
from pathlib import Path

import pytest

import nautical_deliverance.domain as domain_pkg

_DOMAIN = Path(domain_pkg.__file__).parent
_ALLOWED_TOP_LEVEL = frozenset(sys.stdlib_module_names) | {
    "numpy",
    "geographiclib",
    "nautical_deliverance",
}
_OWN_PREFIX = "nautical_deliverance.domain"
_DYNAMIC = {"__import__", "importlib"}


def _import_ok(name: str) -> bool:
    top = name.split(".", maxsplit=1)[0]
    if top == "nautical_deliverance":
        return name == _OWN_PREFIX or name.startswith(f"{_OWN_PREFIX}.")
    return top in _ALLOWED_TOP_LEVEL and top not in _DYNAMIC


def disallowed_imports(source: str) -> list[str]:
    """Return a description of every import in `source` outside the allow-list."""
    bad: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if not _import_ok(a.name)]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                bad.append(f"relative import (level {node.level})")
            elif not _import_ok(node.module or ""):
                bad.append(node.module or "")
        elif isinstance(node, ast.Name) and node.id in _DYNAMIC:
            bad.append(f"dynamic import via {node.id}")
    return bad


def _checked_files() -> list[Path]:
    return sorted(p for sub in ("contracts", "reference") for p in (_DOMAIN / sub).rglob("*.py"))


@pytest.mark.req("S0b-R11")
def test_checked_files_are_found() -> None:
    """The walk covers the real modules (a wrong path would make the allow-list test vacuous)."""
    names = {p.name for p in _checked_files()}
    assert {"geo.py", "weather.py", "performance.py", "uniform_weather.py"} <= names


@pytest.mark.req("S0b-R11")
@pytest.mark.parametrize("path", _checked_files(), ids=lambda p: p.name)
def test_imports_are_on_the_allow_list(path: Path) -> None:
    """Every import of the contracts and the reference implementations is allowed."""
    assert disallowed_imports(path.read_text(encoding="utf-8")) == []


@pytest.mark.req("S0b-R11")
@pytest.mark.parametrize(
    "source",
    [
        "import fastapi",
        "import xarray as xr",
        "from scipy import interpolate",
        "import pydantic.v1",
        "if True:\n    import requests",
        "def f():\n    from pandas import DataFrame",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import sqlalchemy",
        "import nautical_deliverance.api",
        "from nautical_deliverance.persistence import models",
        "from nautical_deliverance import settings",
        "import nautical_deliverance",
        "from . import sibling",
        "from .errors import InvalidInputError",
        "mod = __import__('os')",
        "import importlib",
    ],
)
def test_allow_list_rejects_violating_fixture(source: str) -> None:
    """The check is proven to fail on third-party, own-layer, relative and dynamic imports."""
    assert disallowed_imports(source) != []


@pytest.mark.req("S0b-R11")
@pytest.mark.parametrize(
    "source",
    [
        "import numpy as np\nfrom numpy.typing import NDArray",
        "from geographiclib.geodesic import Geodesic",
        "import math\nfrom collections.abc import Mapping\nfrom dataclasses import dataclass",
        "from nautical_deliverance.domain.contracts.geo import Position",
        "import nautical_deliverance.domain.contracts.units",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from datetime import datetime",
    ],
)
def test_allow_list_accepts_permitted_fixture(source: str) -> None:
    """Stdlib, NumPy, GeographicLib and the engine's own domain package pass."""
    assert disallowed_imports(source) == []
