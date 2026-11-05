"""Contract error types."""


class ContractError(Exception):
    """Base class for all contract errors."""


class InvalidInputError(ContractError):
    """A caller passed input that violates the contract."""


class NaiveDatetimeError(InvalidInputError):
    """A datetime without tzinfo was passed where an aware instant is required."""


class InvalidPositionError(InvalidInputError):
    """A position is outside WGS84 bounds or not finite."""


class MissingRequiredVariableError(ContractError):
    """A weather source lacks variables the consumer requires."""

    def __init__(self, variables: frozenset[str]) -> None:
        """Record the missing variable names."""
        super().__init__(f"missing required variables: {sorted(variables)}")
        self.variables = variables


class DataBlockedError(ContractError):
    """Data is present but must not be used (stale, failed validation, ...)."""

    def __init__(self, reasons: tuple[str, ...]) -> None:
        """Record why the data is blocked."""
        super().__init__(f"data blocked: {', '.join(reasons)}")
        self.reasons = reasons
