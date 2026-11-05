"""Master-data queries (B1-R09)."""

from typing import TYPE_CHECKING, Literal

from sqlalchemy import func, select

from nautical_deliverance.persistence.models import Counterparty, Coverage, Port, Product

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.orm import Session


def counterparties_covering(
    session: Session,
    port_id: uuid.UUID,
    product_ids: Sequence[uuid.UUID],
    *,
    mode: Literal["all", "some"],
) -> list[Counterparty]:
    """Active counterparties covering the port for all, or only some, of the products.

    Inactive ports, products, coverage rows and counterparties never count. An inactive
    requested product is dropped from the request (it can no longer be asked for, so it
    must not make "all" unsatisfiable); if no active product remains, or the port is
    inactive or unknown, the result is empty.
    """
    wanted = set(
        session.scalars(select(Product.id).where(Product.id.in_(set(product_ids)), Product.active))
    )
    port_active = session.scalar(select(Port.id).where(Port.id == port_id, Port.active))
    if not wanted or port_active is None:
        return []
    covered = func.count(func.distinct(Coverage.product_id))
    ids = (
        select(Coverage.counterparty_id)
        .where(Coverage.port_id == port_id, Coverage.product_id.in_(wanted), Coverage.active)
        .group_by(Coverage.counterparty_id)
        .having(covered == len(wanted) if mode == "all" else covered < len(wanted))
    )
    stmt = (
        select(Counterparty)
        .where(Counterparty.id.in_(ids), Counterparty.active)
        .order_by(Counterparty.name, Counterparty.id)
    )
    return list(session.scalars(stmt))
