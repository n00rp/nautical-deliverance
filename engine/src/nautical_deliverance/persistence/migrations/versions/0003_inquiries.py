"""Inquiries, their lines and the monthly reference counter, organization-scoped with RLS.

Revision ID: 0003
Revises: 0002

Same structural isolation as 0002: parents carry UNIQUE (organization_id, id) and every
child references them with a composite FK.
"""

from alembic import op

revision = "0003"
down_revision = "0002"

ORG = "nullif(current_setting('app.organization_id', true), '')::uuid"

STATUSES = "'draft', 'rfq_sent', 'offers_received', 'winner_selected', 'nominated', 'cancelled'"
OLD_ACTIONS = "'create', 'update', 'deactivate', 'reactivate'"
NEW_ACTIONS = f"{OLD_ACTIONS}, 'take', 'cancel', 'duplicate'"


def _fk(table: str, column: str, parent: str, tail: str = "") -> str:
    return (
        f", CONSTRAINT {table}_{column.removesuffix('_id')}_fk FOREIGN KEY"
        f" (organization_id, {column}) REFERENCES {parent} (organization_id, id){tail}"
    )


def _rls(table: str, grants: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY org_isolation ON {table} USING (organization_id = {ORG})"
        f" WITH CHECK (organization_id = {ORG})"
    )
    op.execute(f"GRANT {grants} ON {table} TO nd_app")


def _set_actions(actions: str, tail: str = "") -> None:
    op.execute("ALTER TABLE audit_entry DROP CONSTRAINT audit_entry_action_valid")
    op.execute(
        f"ALTER TABLE audit_entry ADD CONSTRAINT audit_entry_action_valid"
        f" CHECK (action IN ({actions})){tail}"
    )


def upgrade() -> None:
    """Create the inquiry tables and widen the audit actions."""
    op.execute(
        "ALTER TABLE app_user ADD COLUMN name text NOT NULL DEFAULT '',"
        " ADD COLUMN email text NOT NULL DEFAULT '',"
        " ADD COLUMN roles text[] NOT NULL DEFAULT '{}',"
        " ADD CONSTRAINT app_user_org_id_key UNIQUE (organization_id, id)"
    )
    for parent in ("bunkering_reason", "iso_spec_version"):  # not parents in 0002
        op.execute(
            f"ALTER TABLE {parent} ADD CONSTRAINT {parent}_org_id_key UNIQUE (organization_id, id)"
        )
    op.execute(
        "CREATE TABLE inquiry (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        " organization_id uuid NOT NULL REFERENCES organization (id),"
        " reference text NOT NULL, status text NOT NULL DEFAULT 'draft',"
        " vessel_id uuid NOT NULL, legal_entity_id uuid NOT NULL, port_id uuid NOT NULL,"
        " bunkering_reason_id uuid NOT NULL, voyage text,"
        " operator_id uuid NOT NULL, requester_id uuid NOT NULL, buyer_id uuid,"
        " eta timestamptz NOT NULL, etd timestamptz NOT NULL,"
        " agent_name text, agent_email text, internal_comments text, cancel_reason text,"
        " version integer NOT NULL DEFAULT 1,"
        " created_at timestamptz NOT NULL DEFAULT now(), created_by uuid NOT NULL,"
        " updated_at timestamptz NOT NULL DEFAULT now(),"
        " CONSTRAINT inquiry_org_id_key UNIQUE (organization_id, id),"
        " CONSTRAINT inquiry_org_reference_key UNIQUE (organization_id, reference),"
        f" CONSTRAINT inquiry_status_valid CHECK (status IN ({STATUSES})),"
        " CONSTRAINT inquiry_voyage_len CHECK (length(voyage) <= 40),"
        " CONSTRAINT inquiry_etd_after_eta CHECK (etd >= eta),"
        " CONSTRAINT inquiry_comments_len CHECK (length(internal_comments) <= 4000),"
        " CONSTRAINT inquiry_cancel_reason_consistent CHECK"
        " ((status = 'cancelled') = (cancel_reason IS NOT NULL AND btrim(cancel_reason) <> ''))"
        + _fk("inquiry", "vessel_id", "vessel")
        + _fk("inquiry", "legal_entity_id", "legal_entity")
        + _fk("inquiry", "port_id", "port")
        + _fk("inquiry", "bunkering_reason_id", "bunkering_reason")
        + _fk("inquiry", "operator_id", "app_user")
        + _fk("inquiry", "requester_id", "app_user")
        + _fk("inquiry", "buyer_id", "app_user")
        + _fk("inquiry", "created_by", "app_user")
        + ")"
    )
    op.execute(
        "CREATE TABLE inquiry_line (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        " organization_id uuid NOT NULL REFERENCES organization (id),"
        " inquiry_id uuid NOT NULL, position smallint NOT NULL, product_id uuid NOT NULL,"
        " quantity numeric(12,3) NOT NULL, unit text NOT NULL, density numeric(6,1),"
        " spec_notes text, iso_spec_version_id uuid NOT NULL,"
        " CONSTRAINT inquiry_line_position_range CHECK (position BETWEEN 1 AND 10),"
        " CONSTRAINT inquiry_line_quantity_positive CHECK (quantity > 0),"
        " CONSTRAINT inquiry_line_unit_valid CHECK (unit IN ('mt', 'm3')),"
        " CONSTRAINT inquiry_line_density_range CHECK (density BETWEEN 600 AND 1100),"
        " CONSTRAINT inquiry_line_density_only_m3 CHECK (density IS NULL OR unit = 'm3'),"
        " CONSTRAINT inquiry_line_spec_notes_len CHECK (length(spec_notes) <= 500),"
        " CONSTRAINT inquiry_line_inquiry_product_key UNIQUE (inquiry_id, product_id),"
        " CONSTRAINT inquiry_line_inquiry_position_key UNIQUE (inquiry_id, position)"
        + _fk("inquiry_line", "inquiry_id", "inquiry", " ON DELETE CASCADE")
        + _fk("inquiry_line", "product_id", "product")
        + _fk("inquiry_line", "iso_spec_version_id", "iso_spec_version")
        + ")"
    )
    op.execute(
        "CREATE TABLE inquiry_reference_counter ("
        " organization_id uuid NOT NULL REFERENCES organization (id),"
        " year_month char(4) NOT NULL, next_value integer NOT NULL,"
        " PRIMARY KEY (organization_id, year_month))"
    )
    _rls("inquiry", "SELECT, INSERT, UPDATE")
    _rls("inquiry_line", "SELECT, INSERT, UPDATE, DELETE")  # lines are replaced with the draft
    _rls("inquiry_reference_counter", "SELECT, INSERT, UPDATE")
    _set_actions(NEW_ACTIONS)


def downgrade() -> None:
    """Drop everything this revision created, children first."""
    op.execute("DROP TABLE inquiry_reference_counter")
    op.execute("DROP TABLE inquiry_line")
    op.execute("DROP TABLE inquiry")
    # NOT VALID: audit rows with the new actions may exist and the log is append-only.
    _set_actions(OLD_ACTIONS, " NOT VALID")
    for parent in ("bunkering_reason", "iso_spec_version"):
        op.execute(f"ALTER TABLE {parent} DROP CONSTRAINT {parent}_org_id_key")
    op.execute(
        "ALTER TABLE app_user DROP CONSTRAINT app_user_org_id_key, DROP COLUMN roles,"
        " DROP COLUMN email, DROP COLUMN name"
    )
