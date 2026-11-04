"""Unit-suffix gate: every numeric contract field carries its unit."""

import importlib
import inspect
import pkgutil
import types
import typing
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum

import numpy as np
import numpy.typing as npt
import pytest

import nautical_deliverance.domain.contracts as contracts_pkg
from nautical_deliverance.domain.contracts.units import UNIT_SUFFIXES

_ARRAY = npt.NDArray[np.float64]


def contract_dataclasses() -> list[type]:
    """Every dataclass defined in nautical_deliverance.domain.contracts.*."""
    found: list[type] = []
    names = [contracts_pkg.__name__]
    names += [i.name for i in pkgutil.walk_packages(contracts_pkg.__path__, f"{names[0]}.")]
    for name in names:
        mod = importlib.import_module(name)
        found.extend(
            c
            for _, c in inspect.getmembers(mod, inspect.isclass)
            if is_dataclass(c) and c.__module__ == mod.__name__
        )
    return found


def _keys_carry_unit(key_type: object) -> bool:
    """Return True for a StrEnum whose member values all end in a unit suffix."""
    return (
        isinstance(key_type, type)
        and issubclass(key_type, StrEnum)
        and all(m.value.endswith(UNIT_SUFFIXES) for m in key_type)
    )


def _is_numeric(tp: object) -> bool:
    if tp is float or tp == _ARRAY:
        return True
    args = typing.get_args(tp)
    origin = typing.get_origin(tp)
    if origin in (Mapping, dict):
        return not _keys_carry_unit(args[0]) and _is_numeric(args[-1])
    if origin in (typing.Union, types.UnionType):
        return any(_is_numeric(a) for a in args)
    return False


def unsuffixed_numeric_fields(cls: type) -> list[str]:
    """Names of float / float-array / float-mapping fields lacking a unit suffix."""
    hints = typing.get_type_hints(cls)
    return [
        f.name
        for f in fields(cls)
        if _is_numeric(hints[f.name]) and not f.name.endswith(UNIT_SUFFIXES)
    ]


@pytest.mark.req("S0b-R01")
def test_all_contract_fields_suffixed() -> None:
    """No contract dataclass has an unsuffixed numeric field."""
    bad = {c.__name__: unsuffixed_numeric_fields(c) for c in contract_dataclasses()}
    assert {k: v for k, v in bad.items() if v} == {}


@pytest.mark.req("S0b-R01")
def test_gate_rejects_unsuffixed_fixture() -> None:
    """The gate itself catches a bad field, and accepts good ones."""

    @dataclass
    class Bad:
        speed: float
        wind_mps: float
        arr: _ARRAY
        by_name: Mapping[str, float]
        d: dict[str, float]
        m_arr: Mapping[str, _ARRAY]
        opt: float | None
        label: str

    assert unsuffixed_numeric_fields(Bad) == ["speed", "arr", "by_name", "d", "m_arr", "opt"]


@pytest.mark.req("S0b-R01")
def test_from_deg_not_confused_with_deg() -> None:
    """_from_deg is listed (and so matched) before _deg."""
    assert UNIT_SUFFIXES.index("_from_deg") < UNIT_SUFFIXES.index("_deg")
    assert "_from_deg" in UNIT_SUFFIXES


@pytest.mark.req("S0b-R01")
def test_enum_keyed_mapping_accepted_only_if_all_members_suffixed() -> None:
    """A mapping keyed by a fully suffixed StrEnum is accepted; one unsuffixed member rejects it."""

    class Good(StrEnum):
        A = "a_mps"
        B = "b_from_deg"

    class Mixed(StrEnum):
        A = "a_mps"
        B = "b"

    @dataclass
    class Fixture:
        ok: Mapping[Good, _ARRAY]
        bad: Mapping[Mixed, _ARRAY]

    assert unsuffixed_numeric_fields(Fixture) == ["bad"]
