"""Master-data enums and pure validators (B1-D1, B1-D2, B1-D5, B1-D10)."""

import re
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_IMO = re.compile(r"[0-9]{7}")  # explicit class: \d would accept non-ASCII digits
_LOCODE = re.compile(r"[A-Z]{2}[A-Z2-9]{3}")


class CounterpartyType(StrEnum):
    """What a counterparty is (B1-D1)."""

    PHYSICAL_SUPPLIER = "physical_supplier"
    TRADER = "trader"
    BOTH = "both"


class Unit(StrEnum):
    """Quantity unit of a product line (B1-D3)."""

    MT = "mt"
    M3 = "m3"


def imo_valid(imo: str) -> bool:
    """Return whether ``imo`` is seven ASCII digits ending in the IMO check digit."""
    if not _IMO.fullmatch(imo):
        return False
    weighted = sum(int(d) * w for d, w in zip(imo[:6], range(7, 1, -1), strict=True))
    return weighted % 10 == int(imo[6])


def locode_valid(code: str) -> bool:
    """Return whether ``code`` is a UN/LOCODE: two letters then three of A-Z or 2-9."""
    return _LOCODE.fullmatch(code) is not None


def tz_valid(name: str) -> bool:
    """Return whether ``name`` is an IANA zone known to the tz database."""
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError, OSError:
        return False
    return True
