"""Identity schema with row-level security.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None

ORG = "nullif(current_setting('app.organization_id', true), '')::uuid"


def upgrade() -> None:
    """Create organization and app_user, isolated per organization."""
    op.execute("CREATE TABLE organization (id uuid PRIMARY KEY, name text NOT NULL)")
    op.execute(
        "CREATE TABLE app_user (id uuid PRIMARY KEY,"
        " organization_id uuid NOT NULL REFERENCES organization (id),"
        " last_seen_at timestamptz NOT NULL)"
    )
    for table, column in (("organization", "id"), ("app_user", "organization_id")):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY org_isolation ON {table} USING ({column} = {ORG})"
            f" WITH CHECK ({column} = {ORG})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nd_app")


def downgrade() -> None:
    """Drop the identity tables."""
    op.execute("DROP TABLE app_user")
    op.execute("DROP TABLE organization")
