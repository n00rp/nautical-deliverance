"""Identity tables. RLS policies live in migration 0001."""

import uuid  # noqa: TC003 - SQLAlchemy resolves Mapped[] annotations at runtime
from datetime import datetime  # noqa: TC003 - same

from sqlalchemy import DateTime, ForeignKey, Text
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
