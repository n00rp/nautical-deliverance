"""Error hierarchy tests."""

from nautical_deliverance.domain.contracts import errors as e


def test_hierarchy() -> None:
    """Subclass chain matches the contract."""
    assert issubclass(e.InvalidInputError, e.ContractError)
    assert issubclass(e.NaiveDatetimeError, e.InvalidInputError)
    assert issubclass(e.InvalidPositionError, e.InvalidInputError)
    assert issubclass(e.MissingRequiredVariableError, e.ContractError)
    assert issubclass(e.DataBlockedError, e.ContractError)
    assert issubclass(e.ContractError, Exception)


def test_payloads() -> None:
    """Payload attributes are exposed."""
    assert e.MissingRequiredVariableError(frozenset({"wind_u_mps"})).variables == {"wind_u_mps"}
    assert e.DataBlockedError(("stale",)).reasons == ("stale",)
