"""Offers, offer lines and the inquiry decision columns.

Revision ID: 0005
Revises: 0004

Same-inquiry rules are structural: offer carries inquiry_id and references rfq by
(organization_id, inquiry_id, rfq_id); offer_line carries inquiry_id too (denormalised on
purpose) and references offer and inquiry_line by (organization_id, inquiry_id, x_id), so a
line of another inquiry cannot be attached. Only the density rule needs a trigger.
"""

from alembic import op

from nautical_deliverance.domain.offer import DecisionReason, DeliveryMethod

revision = "0005"
down_revision = "0004"

ORG = "nullif(current_setting('app.organization_id', true), '')::uuid"

METHODS = ", ".join(f"'{m.value}'" for m in DeliveryMethod)
REASONS = ", ".join(f"'{r.value}'" for r in DecisionReason)
OLD_ACTIONS = (
    "'create', 'update', 'deactivate', 'reactivate', 'take', 'cancel', 'duplicate',"
    " 'send', 'withdraw', 'decline'"
)
NEW_ACTIONS = f"{OLD_ACTIONS}, 'select_winner'"
COSTS = ("barging_cost", "port_call_cost", "agent_cost", "surveyor_cost", "other_cost")


def _set_actions(actions: str, tail: str = "") -> None:
    op.execute("ALTER TABLE audit_entry DROP CONSTRAINT audit_entry_action_valid")
    op.execute(
        f"ALTER TABLE audit_entry ADD CONSTRAINT audit_entry_action_valid"
        f" CHECK (action IN ({actions})){tail}"
    )


def _rls(table: str, grants: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY org_isolation ON {table} USING (organization_id = {ORG})"
        f" WITH CHECK (organization_id = {ORG})"
    )
    op.execute(f"GRANT {grants} ON {table} TO nd_app")


def upgrade() -> None:
    """Create offer, offer_line, the density trigger and the inquiry decision columns."""
    op.execute(  # targets of the composite FKs
        "ALTER TABLE rfq ADD CONSTRAINT rfq_org_inquiry_id_key"
        " UNIQUE (organization_id, inquiry_id, id)"
    )
    op.execute(
        "ALTER TABLE inquiry_line ADD CONSTRAINT inquiry_line_org_inquiry_id_key"
        " UNIQUE (organization_id, inquiry_id, id)"
    )
    cost_cols = "".join(f" {c} numeric(12,2) NOT NULL DEFAULT 0," for c in COSTS)
    cost_checks = "".join(f" CONSTRAINT offer_{c}_nonneg CHECK ({c} >= 0)," for c in COSTS)
    op.execute(
        "CREATE TABLE offer (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        " organization_id uuid NOT NULL REFERENCES organization (id),"
        " rfq_id uuid NOT NULL, inquiry_id uuid NOT NULL,"
        " currency text NOT NULL DEFAULT 'USD',"
        " valid_until timestamptz NOT NULL,"
        " payment_terms text, delivery_from timestamptz, delivery_to timestamptz,"
        " delivery_method text, physical_supplier text, supplier_comment text,"
        f"{cost_cols}"
        " received_at timestamptz NOT NULL DEFAULT now(),"
        " version integer NOT NULL DEFAULT 1,"
        " created_at timestamptz NOT NULL DEFAULT now(), created_by uuid NOT NULL,"
        " updated_at timestamptz NOT NULL DEFAULT now(),"
        " CONSTRAINT offer_org_id_key UNIQUE (organization_id, id),"
        " CONSTRAINT offer_org_inquiry_id_key UNIQUE (organization_id, inquiry_id, id),"
        " CONSTRAINT offer_rfq_id_key UNIQUE (rfq_id),"
        " CONSTRAINT offer_currency_usd CHECK (currency = 'USD'),"
        " CONSTRAINT offer_payment_terms_len CHECK (length(payment_terms) <= 200),"
        " CONSTRAINT offer_physical_supplier_len CHECK (length(physical_supplier) <= 200),"
        " CONSTRAINT offer_supplier_comment_len CHECK (length(supplier_comment) <= 2000),"
        " CONSTRAINT offer_delivery_order CHECK (delivery_from <= delivery_to),"
        f" CONSTRAINT offer_delivery_method_valid CHECK (delivery_method IN ({METHODS})),"
        f"{cost_checks}"
        " CONSTRAINT offer_rfq_fk FOREIGN KEY (organization_id, inquiry_id, rfq_id)"
        " REFERENCES rfq (organization_id, inquiry_id, id),"
        " CONSTRAINT offer_inquiry_fk FOREIGN KEY (organization_id, inquiry_id)"
        " REFERENCES inquiry (organization_id, id),"
        " CONSTRAINT offer_created_by_fk FOREIGN KEY (organization_id, created_by)"
        " REFERENCES app_user (organization_id, id))"
    )
    op.execute(
        "CREATE TABLE offer_line (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        " organization_id uuid NOT NULL REFERENCES organization (id),"
        " offer_id uuid NOT NULL, inquiry_id uuid NOT NULL, inquiry_line_id uuid NOT NULL,"
        " price_per_mt numeric(12,3) NOT NULL, density numeric(6,1),"
        " CONSTRAINT offer_line_one_per_line_key UNIQUE (offer_id, inquiry_line_id),"
        " CONSTRAINT offer_line_price_positive CHECK (price_per_mt > 0),"
        " CONSTRAINT offer_line_density_range CHECK (density BETWEEN 600 AND 1100),"
        " CONSTRAINT offer_line_offer_fk FOREIGN KEY (organization_id, inquiry_id, offer_id)"
        " REFERENCES offer (organization_id, inquiry_id, id) ON DELETE CASCADE,"
        " CONSTRAINT offer_line_inquiry_line_fk FOREIGN KEY"
        " (organization_id, inquiry_id, inquiry_line_id)"
        " REFERENCES inquiry_line (organization_id, inquiry_id, id))"
    )
    op.execute(
        "CREATE FUNCTION offer_line_density_fn() RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN"
        " IF NEW.density IS NOT NULL AND NOT EXISTS (SELECT 1 FROM inquiry_line il"
        " WHERE il.id = NEW.inquiry_line_id AND il.unit = 'm3' AND il.density IS NULL) THEN"
        " RAISE EXCEPTION 'offer_line_density_allowed: density only for an m3 line without"
        " density' USING ERRCODE = 'integrity_constraint_violation';"
        " END IF;"
        " RETURN NEW; END; $$"
    )
    op.execute(
        "CREATE TRIGGER offer_line_density_allowed BEFORE INSERT OR UPDATE ON offer_line"
        " FOR EACH ROW EXECUTE FUNCTION offer_line_density_fn()"
    )
    _rls("offer", "SELECT, INSERT, UPDATE")
    _rls("offer_line", "SELECT, INSERT, UPDATE, DELETE")  # lines are replaced as a set
    op.execute(
        "ALTER TABLE inquiry ADD COLUMN winner_offer_id uuid, ADD COLUMN decision_reason text,"
        " ADD COLUMN decision_note text, ADD COLUMN decided_at timestamptz,"
        " ADD COLUMN decided_by uuid, ADD COLUMN decided_total numeric(14,2),"
        f" ADD CONSTRAINT inquiry_decision_reason_valid CHECK (decision_reason IN ({REASONS})),"
        " ADD CONSTRAINT inquiry_decision_note_len CHECK (length(decision_note) <= 2000),"
        " ADD CONSTRAINT inquiry_decision_consistent CHECK ("
        " ((winner_offer_id IS NULL) = (decided_at IS NULL)"
        " AND (winner_offer_id IS NULL) = (decided_by IS NULL)"
        " AND (winner_offer_id IS NULL) = (decided_total IS NULL))"
        " AND (winner_offer_id IS NOT NULL"
        " OR (decision_reason IS NULL AND decision_note IS NULL))),"
        " ADD CONSTRAINT inquiry_winner_fk FOREIGN KEY (organization_id, id, winner_offer_id)"
        " REFERENCES offer (organization_id, inquiry_id, id),"
        " ADD CONSTRAINT inquiry_decided_by_fk FOREIGN KEY (organization_id, decided_by)"
        " REFERENCES app_user (organization_id, id)"
    )
    _set_actions(NEW_ACTIONS)


def downgrade() -> None:
    """Drop everything this revision created."""
    op.execute(  # drops the columns' constraints with them
        "ALTER TABLE inquiry DROP COLUMN winner_offer_id, DROP COLUMN decision_reason,"
        " DROP COLUMN decision_note, DROP COLUMN decided_at, DROP COLUMN decided_by,"
        " DROP COLUMN decided_total"
    )
    op.execute("DROP TABLE offer_line")
    op.execute("DROP FUNCTION offer_line_density_fn()")
    op.execute("DROP TABLE offer")
    # NOT VALID: audit rows with the new action may exist and the log is append-only.
    _set_actions(OLD_ACTIONS, " NOT VALID")
    op.execute("ALTER TABLE inquiry_line DROP CONSTRAINT inquiry_line_org_inquiry_id_key")
    op.execute("ALTER TABLE rfq DROP CONSTRAINT rfq_org_inquiry_id_key")
