"""Operator becomes a name (B7-D10): inquiry.operator_name and vessel.default_operator_name.

Revision ID: 0007
Revises: 0006

The names are copied from app_user (name, else e-mail, like inquiry_repo._shown) before the id
columns are dropped. FORCE RLS binds nd_owner too and no organization is set during a
migration, so the copy would see no rows: RLS is relaxed to ENABLE for the three tables inside
this revision's transaction and forced again before it commits. Table-level grants (0002, 0003)
cover the new columns. The downgrade cannot restore the ids: the id columns come back null.
"""

from alembic import op

revision = "0007"
down_revision = "0006"

TABLES = ("inquiry", "vessel", "app_user")


def upgrade() -> None:
    """Add the name columns, copy the operators' names, drop the id columns."""
    op.execute(
        "ALTER TABLE inquiry ADD COLUMN operator_name text,"
        " ADD CONSTRAINT inquiry_operator_name_len CHECK (char_length(operator_name) <= 120)"
    )
    op.execute(
        "ALTER TABLE vessel ADD COLUMN default_operator_name text,"
        " ADD CONSTRAINT vessel_default_operator_name_len"
        " CHECK (char_length(default_operator_name) <= 120)"
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(
        # name, else e-mail (inquiry_repo._shown); left(): the column check is 120
        "UPDATE inquiry i SET operator_name = left(coalesce(nullif(u.name, ''), u.email), 120)"
        " FROM app_user u WHERE u.id = i.operator_id"
    )
    op.execute(
        "UPDATE vessel v"
        " SET default_operator_name = left(coalesce(nullif(u.name, ''), u.email), 120)"
        " FROM app_user u"
        " WHERE u.id = v.default_operator AND u.organization_id = v.organization_id"
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inquiry DROP COLUMN operator_id")  # drops inquiry_operator_fk
    op.execute("ALTER TABLE vessel DROP COLUMN default_operator")


def downgrade() -> None:
    """Bring back the id columns (nullable, empty) and drop the name columns."""
    op.execute(
        "ALTER TABLE inquiry ADD COLUMN operator_id uuid REFERENCES app_user (id),"
        " DROP COLUMN operator_name"
    )
    op.execute(
        "ALTER TABLE vessel ADD COLUMN default_operator uuid, DROP COLUMN default_operator_name"
    )
