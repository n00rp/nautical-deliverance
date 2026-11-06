"""Dashboard REST API (B5-D4..D6, D11): what needs attention, status counts, the month's figures.

Every role may read it. The Operator gets only status counts and ETA items without detail, and no
month figures: nothing is queried for them beyond that, so nothing commercial can leak.
"""

import uuid  # noqa: TC003  (pydantic runtime)
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from nautical_deliverance.api.access import Eng, Now  # noqa: TC001
from nautical_deliverance.api.common import eta_warning, scope, sees_rfqs
from nautical_deliverance.api.inquiries import Reader  # noqa: TC001
from nautical_deliverance.persistence import dashboard_repo

router = APIRouter()
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class AttentionItem(BaseModel):
    """One thing that needs the user's attention, linking to its inquiry."""

    inquiry_id: uuid.UUID
    reference: str
    vessel_name: str
    port_name: str
    kind: Literal["rfq_deadline", "offer_validity", "eta_unnominated", "rfq_drafts_unsent"]
    due_at: datetime | None
    detail: str | None


class MonthOut(BaseModel):
    """Figures of the UTC calendar month; amounts are decimal strings."""

    period: str
    nominated_mt: str
    mt_excluded_lines: int
    nominated_spend: str
    currency: str
    open_by_status: dict[str, int]
    avg_offers: str | None


class DashboardOut(BaseModel):
    """The dashboard; `month` is null for the Operator."""

    attention: list[AttentionItem]
    status_counts: dict[str, int]
    month: MonthOut | None


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(principal: Reader, engine: Eng, now: Now) -> object:
    """Attention list (earliest due first), status counts and month figures, by role."""
    with scope(principal, engine) as s:
        items = dashboard_repo.eta_items(s, now, eta_warning)
        month = None
        if sees_rfqs(principal):
            items += dashboard_repo.rfq_items(s, now) + dashboard_repo.validity_items(s, now)
            month = dashboard_repo.month_figures(s, now)
        items.sort(
            key=lambda i: (i["due_at"] is None, i["due_at"] or EPOCH, i["reference"], i["kind"])
        )
        return {
            "attention": items,
            "status_counts": dashboard_repo.status_counts(s),
            "month": month,
        }
