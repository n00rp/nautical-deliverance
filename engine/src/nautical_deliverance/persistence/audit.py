"""Audit helper (B1-D12): one entry per change, in the caller's transaction."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Literal

from sqlalchemy import literal_column

from nautical_deliverance.persistence.models import AuditEntry

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from sqlalchemy.orm import Session

Action = Literal["create", "update", "deactivate", "reactivate"]


def _text(value: object) -> str | None:  # noqa: PLR0911
    """Canonical string form, so equal values compare equal and diffs stay stable.

    Enum -> its value; bool -> "true"/"false"; Decimal without trailing zeros;
    datetime -> ISO UTC with "Z" (naive is a programming error); list/tuple -> JSON
    array in order; set/frozenset -> JSON array sorted by canonical element string.
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return _text(value.value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            msg = "naive datetime in audit values; use a timezone-aware one"
            raise ValueError(msg)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_text(v) for v in value]
        if isinstance(value, (set, frozenset)):
            items.sort(key=lambda t: (t is None, t or ""))
        return json.dumps(items)
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
