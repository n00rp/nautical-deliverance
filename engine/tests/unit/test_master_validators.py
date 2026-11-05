"""Pure master-data validators (B1-R03, B1-R02)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nautical_deliverance.domain.master import (
    CounterpartyType,
    Unit,
    imo_valid,
    locode_valid,
    tz_valid,
)


def _check_digit(six: str) -> int:
    return sum(int(d) * w for d, w in zip(six, range(7, 1, -1), strict=True)) % 10


@pytest.mark.req("B1-R03")
@settings(max_examples=1000)
@given(six=st.integers(min_value=0, max_value=999_999).map(lambda n: f"{n:06d}"))
def test_imo_check_digit_property(six: str) -> None:
    """Only the computed check digit is accepted as the 7th digit."""
    good = _check_digit(six)
    for digit in range(10):
        assert imo_valid(f"{six}{digit}") is (digit == good)


@pytest.mark.req("B1-R03")
@pytest.mark.parametrize(
    ("imo", "ok"),
    [
        ("9074729", True),
        ("9074728", False),
        ("907472", False),
        ("90747290", False),
        ("abcdefg", False),
        ("", False),
        ("\uff19\uff10\uff17\uff14\uff17\uff12\uff19", False),
        ("9074729\n", False),
    ],
)
def test_imo_examples(imo: str, ok: bool) -> None:  # noqa: FBT001
    """Known IMO numbers and malformed input."""
    assert imo_valid(imo) is ok


@pytest.mark.req("B1-R02")
@pytest.mark.parametrize(
    ("code", "ok"),
    [
        ("NLRTM", True),
        ("SGSIN", True),
        ("USHOU", True),
        ("AE2J3", True),
        ("nlrtm", False),
        ("NLRT", False),
        ("NLRTMX", False),
        ("NL1TM", False),
        ("NLRT1", False),
        ("NLRTM\n", False),
        ("", False),
    ],
)
def test_locode_table(code: str, ok: bool) -> None:  # noqa: FBT001
    """LOCODE: two letters, then three of A-Z or 2-9."""
    assert locode_valid(code) is ok


@pytest.mark.req("B1-R02")
@pytest.mark.parametrize(
    ("name", "ok"),
    [
        ("Europe/Amsterdam", True),
        ("UTC", True),
        ("Mars/Olympus", False),
        ("", False),
        ("../etc/passwd", False),
    ],
)
def test_tz(name: str, ok: bool) -> None:  # noqa: FBT001
    """IANA zone names resolve via zoneinfo."""
    assert tz_valid(name) is ok


def test_enums() -> None:
    """Enum values are the stored strings."""
    assert [c.value for c in CounterpartyType] == ["physical_supplier", "trader", "both"]
    assert [u.value for u in Unit] == ["mt", "m3"]
