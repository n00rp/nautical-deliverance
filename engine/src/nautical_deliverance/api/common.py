"""Helpers shared by the API routers: scoped transactions, error shapes, validators."""

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import psycopg.errors
from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, ConfigDict
from sqlalchemy import Engine  # noqa: TC002
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session  # noqa: TC002

from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.domain.inquiry import Status
from nautical_deliverance.domain.rfq import single_address
from nautical_deliverance.persistence.db import org_session

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.exceptions import RequestValidationError

DB_DOWN = "Database unavailable"
STALE = "Record was changed by someone else"
ETA_WARNING_WINDOW = timedelta(hours=48)
RFQ_READERS = frozenset({Role.BUNKER_BUYER, Role.ADMIN, Role.VIEWER})


def eta_warning(state: str, eta: datetime | None, now: datetime) -> bool:
    """Return the B2 ETA warning: an open inquiry whose ETA is inside the window (or passed)."""
    if eta is None:
        return False
    open_ = state not in (Status.NOMINATED, Status.CANCELLED)
    return open_ and eta < now + ETA_WARNING_WINDOW


def sees_rfqs(principal: Principal) -> bool:
    """Only RFQ readers may learn who or how many suppliers were contacted (R6)."""
    return bool(RFQ_READERS & principal.roles)


def _field(loc: tuple[int | str, ...]) -> str:
    """Error location without the "body"/"query" prefix: ``lines[0].quantity``, ``items.name``."""
    out = ""
    for part in loc[1:]:
        out += f"[{part}]" if isinstance(part, int) else f"{'.' if out else ''}{part}"
    return out


def field_errors(exc: RequestValidationError) -> JSONResponse:
    """422 as {"detail": [{"field", "message"}]} for every validation failure."""
    detail = [
        {
            "field": _field(err["loc"]),
            "message": str(err["msg"]).removeprefix("Value error, "),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        {"detail": jsonable_encoder(detail)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
    )


def validation_handler(_: Request, exc: Exception) -> JSONResponse:
    """Exception handler registered by the app factory."""
    return field_errors(cast("RequestValidationError", exc))


def unprocessable(field: str, message: str) -> HTTPException:
    """Build a 422 for one field."""
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, [{"field": field, "message": message}]
    )


def conflict() -> HTTPException:
    """409: the record was changed by someone else."""
    return HTTPException(status.HTTP_409_CONFLICT, STALE)


# Violated constraint name -> (field, message). Unknown constraints stay a 500 (a real bug).
CONSTRAINTS = {
    "legal_entity_org_code_key": ("code", "Code already exists"),
    "port_org_locode_key": ("locode", "LOCODE already exists"),
    "vessel_org_imo_key": ("imo", "IMO already exists"),
    "product_org_name_key": ("name", "Name already exists"),
    "iso_spec_version_org_name_key": ("name", "Name already exists"),
    "bunkering_reason_org_name_key": ("name", "Name already exists"),
    "vessel_legal_entity_fk": ("legal_entity_id", "Unknown legal entity"),
    "contact_one_primary_idx": ("is_primary", "Counterparty already has an active primary contact"),
    "coverage_org_cp_port_product_key": ("items", "Duplicate coverage entry"),
    "coverage_port_fk": ("items.port_id", "Unknown port"),
    "coverage_product_fk": ("items.product_id", "Unknown product"),
    "vessel_approved_fuel_org_vessel_product_key": ("items", "Duplicate approved fuel"),
    "vessel_approved_fuel_product_fk": ("items.product_id", "Unknown product"),
    "offer_rfq_id_key": ("rfq_id", "Offer already entered"),
    "offer_delivery_order": ("delivery_to", "Must not be before delivery_from"),
    "offer_line_one_per_line_key": ("lines", "Duplicate inquiry line"),
}


@contextmanager
def scope(principal: Principal, engine: Engine) -> Iterator[Session]:
    """Organization-scoped transaction mapping database failures to HTTP errors."""
    try:
        with org_session(principal.organization_id, engine) as session:
            yield session
    except OperationalError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, DB_DOWN) from exc
    except IntegrityError as exc:
        diag = exc.orig.diag if isinstance(exc.orig, psycopg.Error) else None
        mapped = CONSTRAINTS.get(diag.constraint_name or "") if diag else None
        if mapped is None:
            raise
        raise unprocessable(*mapped) from exc


def check(ok: Any, message: str) -> AfterValidator:  # noqa: ANN401
    """Pydantic validator that raises `message` when `ok(value)` is false."""

    def validate(value: str) -> str:
        if not ok(value):
            raise ValueError(message)
        return value

    return AfterValidator(validate)


def email_ok(value: str) -> bool:
    """Plausible e-mail address."""
    domain = value.partition("@")[2]
    return (
        len(value) <= 254  # noqa: PLR2004
        and single_address(value)
        and "." in domain
        and all(domain.split("."))
    )


class Strict(BaseModel):
    """No unknown fields: actor/at/organization can never be supplied by a client."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)
