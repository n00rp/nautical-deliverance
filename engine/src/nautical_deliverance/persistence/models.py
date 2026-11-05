"""Identity and master-data tables. RLS policies live in migrations 0001 and 0002."""

import uuid
from datetime import datetime  # noqa: TC003 - same
from decimal import Decimal  # noqa: TC003 - SQLAlchemy resolves annotations at runtime

from sqlalchemy import DateTime, ForeignKey, Numeric, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, CHAR, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base."""


class Organization(Base):
    """A tenant."""

    __tablename__ = "organization"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)


class AppUser(Base):
    """A user; id is the Keycloak subject."""

    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    name: Mapped[str] = mapped_column(Text, server_default=text("''"))
    email: Mapped[str] = mapped_column(Text, server_default=text("''"))
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))


class _Master:
    """Columns shared by every master-data table."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    version: Mapped[int] = mapped_column(server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LegalEntity(_Master, Base):
    """A company that owns vessels."""

    __tablename__ = "legal_entity"

    name: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(Text)


class Product(_Master, Base):
    """A fuel product."""

    __tablename__ = "product"

    name: Mapped[str] = mapped_column(Text)
    default_unit: Mapped[str] = mapped_column(Text, server_default=text("'mt'"))


class Port(_Master, Base):
    """A port by UN/LOCODE with its IANA time zone."""

    __tablename__ = "port"

    locode: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(Text)
    time_zone: Mapped[str] = mapped_column(Text)


class Counterparty(_Master, Base):
    """A supplier, trader or both."""

    __tablename__ = "counterparty"

    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class IsoSpecVersion(_Master, Base):
    """An ISO 8217 edition."""

    __tablename__ = "iso_spec_version"

    name: Mapped[str] = mapped_column(Text)


class BunkeringReason(_Master, Base):
    """Why bunkers are taken."""

    __tablename__ = "bunkering_reason"

    name: Mapped[str] = mapped_column(Text)


class Vessel(_Master, Base):
    """A vessel; default_operator is a Keycloak user id (no FK)."""

    __tablename__ = "vessel"

    name: Mapped[str] = mapped_column(Text)
    imo: Mapped[str] = mapped_column(Text)
    vessel_type: Mapped[str] = mapped_column(Text)
    dwt: Mapped[int]
    flag: Mapped[str] = mapped_column(Text)
    legal_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entity.id"))
    default_operator: Mapped[uuid.UUID | None]


class VesselApprovedFuel(_Master, Base):
    """A product a vessel may take."""

    __tablename__ = "vessel_approved_fuel"

    vessel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vessel.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))


class Contact(_Master, Base):
    """A person at a counterparty."""

    __tablename__ = "contact"

    counterparty_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("counterparty.id"))
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(server_default=text("false"))


class Coverage(_Master, Base):
    """A counterparty can supply a product at a port."""

    __tablename__ = "coverage"

    counterparty_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("counterparty.id"))
    port_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("port.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))


class AuditEntry(Base):
    """Append-only change log: nd_app has SELECT and INSERT only."""

    __tablename__ = "audit_entry"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    actor: Mapped[uuid.UUID]
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID]
    action: Mapped[str] = mapped_column(Text)
    changes: Mapped[dict[str, dict[str, str | None]]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )


class Inquiry(Base):
    """A bunker inquiry; DB FKs are composite (organization_id, x_id)."""

    __tablename__ = "inquiry"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    reference: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    vessel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vessel.id"))
    legal_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entity.id"))
    port_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("port.id"))
    bunkering_reason_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bunkering_reason.id"))
    voyage: Mapped[str | None] = mapped_column(Text)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    etd: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    agent_name: Mapped[str | None] = mapped_column(Text)
    agent_email: Mapped[str | None] = mapped_column(Text)
    internal_comments: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InquiryLine(Base):
    """One product line of an inquiry (1..10)."""

    __tablename__ = "inquiry_line"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    inquiry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inquiry.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(Text)
    density: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    spec_notes: Mapped[str | None] = mapped_column(Text)
    iso_spec_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iso_spec_version.id"))


class InquiryReferenceCounter(Base):
    """Next sequence number per organization and UTC month (yymm)."""

    __tablename__ = "inquiry_reference_counter"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), primary_key=True
    )
    year_month: Mapped[str] = mapped_column(CHAR(4), primary_key=True)
    next_value: Mapped[int]
