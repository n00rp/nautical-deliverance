"""Audit helper (B1-D12): one entry per change, in the caller's transaction."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from sqlalchemy import literal_column

from nautical_deliverance.persistence.models import AuditEntry

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from sqlalchemy.orm import Session

Action = Literal["create", "update", "deactivate", "reactivate"]


def _text(value: object) -> str | None:
    """Canonical string form: Decimals without trailing zeros, datetimes as ISO UTC."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def record_change(  # noqa: PLR0913
    session: Session,
    *,
    actor: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    action: Action,
    before: Mapping[str, object] | None,
    after: Mapping[str, object],
) -> AuditEntry | None:
    """Add one per-field before/after entry; None (and no row) when nothing changed.

    `at` is the database clock and the organization is the session's RLS scope;
    neither can be supplied by the caller.
    """
    old = before or {}
    changes = {
        k: {"before": _text(old.get(k)), "after": _text(v)}
        for k, v in after.items()
        if _text(old.get(k)) != _text(v)
    }
    if not changes:
        return None
    entry = AuditEntry(
        # Scope taken from the RLS setting, so an entry can never name another org.
        organization_id=literal_column(
            "nullif(current_setting('app.organization_id', true), '')::uuid"
        ),
        actor=actor,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        changes=changes,
    )
    session.add(entry)
    session.flush()
    session.refresh(entry)
    return entry
