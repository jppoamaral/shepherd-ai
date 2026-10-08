"""Declarative base and helpers shared by every model.

Tenancy is enforced in the schema, not only in queries: every tenant-owned table
carries `church_id`, exposes a `(church_id, id)` unique key, and references other
tenant-owned rows through composite foreign keys on `(church_id, <fk>)`. The
database therefore rejects a row that links two churches.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def enum_column(enum: type[StrEnum]) -> sa.Enum:
    """Store a StrEnum as text guarded by a CHECK constraint (no native PG enum types)."""
    return sa.Enum(
        enum,
        native_enum=False,
        create_constraint=True,
        length=32,
        name=enum.__name__.lower(),
        values_callable=lambda e: [member.value for member in e],
    )


def tenant_fk(column: str, target_table: str) -> sa.ForeignKeyConstraint:
    """Composite FK `(church_id, column) -> target_table(church_id, id)`.

    With Postgres' default MATCH SIMPLE a NULL `column` skips the check, so this
    works for optional references too.
    """
    return sa.ForeignKeyConstraint(
        ["church_id", column],
        [f"{target_table}.church_id", f"{target_table}.id"],
    )


class TenantMixin:
    """Primary key, owning church, and the `(church_id, id)` key for composite FKs."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    church_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("churches.id"), index=True)

    @declared_attr.directive
    def __table_args__(cls) -> Any:
        return (sa.UniqueConstraint("church_id", "id"), *getattr(cls, "__extra_args__", ()))


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
