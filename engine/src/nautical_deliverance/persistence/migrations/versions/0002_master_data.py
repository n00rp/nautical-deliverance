"""Master data and append-only audit log, organization-scoped with RLS.

Revision ID: 0002
Revises: 0001

Every parent has UNIQUE (organization_id, id) and every child references it with a
composite FK, so a row can never point at another organization's parent (FK checks
bypass RLS, so this must be structural).
"""

from alembic import op

revision = "0002"
down_revision = "0001"

ORG = "nullif(current_setting('app.organization_id', true), '')::uuid"

# Creation order = dependency order.
MASTER = (
    "legal_entity",
    "product",
    "port",
    "counterparty",
    "iso_spec_version",
    "bunkering_reason",
    "vessel",
    "vessel_approved_fuel",
    "contact",
    "coverage",
)

COMMON = (
    "id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    " organization_id uuid NOT NULL REFERENCES organization (id),"
    " active boolean NOT NULL DEFAULT true,"
    " version integer NOT NULL DEFAULT 1,"
    " created_at timestamptz NOT NULL DEFAULT now(),"
    " updated_at timestamptz NOT NULL DEFAULT now()"
)


def _fk(table: str, column: str, parent: str) -> str:
    return (
        f", CONSTRAINT {table}_{column.removesuffix('_id')}_fk FOREIGN KEY"
        f" (organization_id, {column}) REFERENCES {parent} (organization_id, id)"
    )


DDL = {
    "legal_entity": (
        "name text NOT NULL, code text NOT NULL, CONSTRAINT legal_entity_org_code_key"
        " UNIQUE (organization_id, code)"
    ),
    "product": (
        "name text NOT NULL, default_unit text NOT NULL DEFAULT 'mt',"
        " CONSTRAINT product_default_unit_valid CHECK (default_unit IN ('mt', 'm3')),"
        " CONSTRAINT product_org_name_key UNIQUE (organization_id, name)"
    ),
    "port": (
        "locode text NOT NULL, name text NOT NULL, country text NOT NULL, time_zone text NOT NULL,"
        " CONSTRAINT port_locode_format CHECK (locode ~ '^[A-Z]{2}[A-Z2-9]{3}$'),"
        " CONSTRAINT port_country_format CHECK (country ~ '^[A-Z]{2}$'),"
        " CONSTRAINT port_org_locode_key UNIQUE (organization_id, locode)"
    ),
    "counterparty": (
        "name text NOT NULL, type text NOT NULL, notes text,"
        " CONSTRAINT counterparty_type_valid"
        " CHECK (type IN ('physical_supplier', 'trader', 'both'))"
    ),
    "iso_spec_version": (
        "name text NOT NULL,"
        " CONSTRAINT iso_spec_version_org_name_key UNIQUE (organization_id, name)"
    ),
    "bunkering_reason": (
        "name text NOT NULL,"
        " CONSTRAINT bunkering_reason_org_name_key UNIQUE (organization_id, name)"
    ),
    "vessel": (
        "name text NOT NULL, imo text NOT NULL, vessel_type text NOT NULL, dwt integer NOT NULL,"
        " flag text NOT NULL, legal_entity_id uuid NOT NULL,"
        " default_operator uuid,"  # Keycloak user id; no FK, the user may not have logged in yet
        " CONSTRAINT vessel_imo_format CHECK (imo ~ '^[0-9]{7}$'),"
        " CONSTRAINT vessel_dwt_positive CHECK (dwt > 0),"
        " CONSTRAINT vessel_org_imo_key UNIQUE (organization_id, imo)"
        + _fk("vessel", "legal_entity_id", "legal_entity")
    ),
    "vessel_approved_fuel": (
        "vessel_id uuid NOT NULL, product_id uuid NOT NULL,"
        " CONSTRAINT vessel_approved_fuel_org_vessel_product_key"
        " UNIQUE (organization_id, vessel_id, product_id)"
        + _fk("vessel_approved_fuel", "vessel_id", "vessel")
        + _fk("vessel_approved_fuel", "product_id", "product")
    ),
    "contact": (
        "counterparty_id uuid NOT NULL, name text NOT NULL, email text NOT NULL, phone text,"
        " is_primary boolean NOT NULL DEFAULT false"
        + _fk("contact", "counterparty_id", "counterparty")
    ),
    "coverage": (
        "counterparty_id uuid NOT NULL, port_id uuid NOT NULL, product_id uuid NOT NULL,"
        " CONSTRAINT coverage_org_cp_port_product_key"
        " UNIQUE (organization_id, counterparty_id, port_id, product_id)"
        + _fk("coverage", "counterparty_id", "counterparty")
        + _fk("coverage", "port_id", "port")
        + _fk("coverage", "product_id", "product")
    ),
}

# Referenced by composite FKs.
PARENTS = ("legal_entity", "product", "port", "counterparty", "vessel")


def _rls(table: str, grants: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY org_isolation ON {table} USING (organization_id = {ORG})"
        f" WITH CHECK (organization_id = {ORG})"
    )
    op.execute(f"GRANT {grants} ON {table} TO nd_app")  # never DELETE


def upgrade() -> None:
    """Create the master-data tables and the audit log."""
    for table in MASTER:
        extra = (
            f", CONSTRAINT {table}_org_id_key UNIQUE (organization_id, id)"
            if table in PARENTS
            else ""
        )
        op.execute(f"CREATE TABLE {table} ({COMMON}, {DDL[table]}{extra})")
        _rls(table, "SELECT, INSERT, UPDATE")
    op.execute(  # at most one active primary contact per counterparty
        "CREATE UNIQUE INDEX contact_one_primary_idx ON contact (organization_id, counterparty_id)"
        " WHERE is_primary AND active"
    )
    op.execute(
        "CREATE TABLE audit_entry (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        " organization_id uuid NOT NULL REFERENCES organization (id),"
        " actor uuid NOT NULL, at timestamptz NOT NULL DEFAULT now(),"
        " entity_type text NOT NULL, entity_id uuid NOT NULL, action text NOT NULL,"
        " changes jsonb NOT NULL DEFAULT '{}'::jsonb,"
        " CONSTRAINT audit_entry_action_valid"
        " CHECK (action IN ('create', 'update', 'deactivate', 'reactivate')))"
    )
    op.execute(
        "CREATE INDEX audit_entry_entity_idx"
        " ON audit_entry (organization_id, entity_type, entity_id, at DESC)"
    )
    _rls("audit_entry", "SELECT, INSERT")  # append-only (B1-D12)


def downgrade() -> None:
    """Drop everything this revision created, children first."""
    op.execute("DROP TABLE audit_entry")
    for table in reversed(MASTER):
        op.execute(f"DROP TABLE {table}")
