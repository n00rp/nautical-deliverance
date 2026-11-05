"""Equality and hashing for contract value types that hold mappings (see the package docstring)."""

from collections.abc import Mapping
from dataclasses import fields


def canonical(value: object) -> object:
    """Return a hashable, order-independent form: mappings become sorted tuples, recursively."""
    if isinstance(value, Mapping):
        items = ((k, canonical(v)) for k, v in value.items())
        return tuple(sorted(items, key=lambda kv: str(kv[0])))
    if isinstance(value, tuple | list):
        return tuple(canonical(v) for v in value)
    return value


class ValueEquality:
    """Mixin for dataclasses declared with `eq=False`: compare and hash by canonical field values.

    A frozen dataclass holding a `Mapping` cannot use the generated `__hash__` (mappings are not
    hashable); this makes instances usable as `dict` keys and `functools.lru_cache` arguments.
    """

    __slots__ = ()

    def _key(self) -> tuple[object, ...]:
        return tuple(canonical(getattr(self, f.name)) for f in fields(self))  # type: ignore[arg-type]

    def __eq__(self, other: object) -> bool:
        """Equal when both are the same type with equal canonical field values."""
        if type(other) is not type(self):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        """Hash of the canonical field values."""
        return hash(self._key())
