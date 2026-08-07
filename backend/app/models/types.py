"""Reusable column types shared by the ORM models."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeEngine

from app.core.enums import ENUM_LENGTH

#: JSON storage that becomes JSONB on PostgreSQL (indexable, binary) and plain
#: JSON everywhere else, so the SQLite-backed test suite still works.
JSONVariant: TypeEngine[dict[str, object]] = JSON().with_variant(JSONB, "postgresql")


def enum_column(enum_cls: type[StrEnum]) -> SAEnum:
    """Build a VARCHAR-backed enum column with a CHECK constraint.

    ``values_callable`` makes SQLAlchemy persist the enum *values*
    (``"missing_sot"``) rather than the member *names* (``"MISSING_SOT"``),
    which keeps stored data readable and matches the API representation.

    ``create_constraint=True`` is required and not the default: without it
    SQLAlchemy emits a bare ``VARCHAR`` with no validation, so raw SQL or a
    future migration could write a value the application cannot parse.
    ``name`` gives the generated constraint a stable identifier for the
    ``ck_%(table_name)s_%(constraint_name)s`` naming convention.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        name=enum_cls.__name__.lower(),
        length=ENUM_LENGTH,
        values_callable=lambda enum: [member.value for member in enum],
        validate_strings=True,
    )
