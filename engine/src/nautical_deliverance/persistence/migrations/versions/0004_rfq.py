"""RFQ table: one per inquiry and supplier, with a frozen sent snapshot.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

from nautical_deliverance.domain.rfq import RfqStatus

revision = "0004"
down_revision = "0003"

ORG = "nullif(current_setting('app.organization_id', true), '')::uuid"

STATUSES = ", ".join(f"'{s.value}'" for s in RfqStatus)
OLD_ACTIONS = "'create', 'update', 'deactivate', 'reactivate', 'take', 'cancel', 'duplicate'"
NEW_ACTIONS = f"{OLD_ACTIONS}, 'send', 'withdraw', 'decline'"
SENT = "sent_at, sent_to_email, sent_subject, sent_body"


def _set_actions(actions: str, tail: str = "") -> None:
    op.execute("ALTER TABLE audit_entry DROP CONSTRAINT audit_entry_action_valid")
    op.execute(
        f"ALTER TABLE audit_entry ADD CONSTRAINT audit_entry_action_valid"
        f" CHECK (action IN ({actions})){tail}"
    )


def upgrade() -> None:
    """Create rfq, its guard trigger and RLS; widen the audit actions."""
    op.execute("ALTER TABLE inquiry ADD COLUMN rfq_deadline timestamptz")
    op.execute(  # target of the contact-belongs-to-counterparty FK
        "ALTER TABLE contact ADD CONSTRAINT contact_org_cp_id_key"
        " UNIQUE (organization_id, counterparty_id, id)"
    )
    op.execute(
        "CREATE TABLE rfq (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        " organization_id uuid NOT NULL REFERENCES organization (id),"
        " inquiry_id uuid NOT NULL, counterparty_id uuid NOT NULL, contact_id uuid NOT NULL,"
        " status text NOT NULL DEFAULT 'draft',"
        " response_deadline timestamptz NOT NULL, generated_at timestamptz NOT NULL,"
        " sent_at timestamptz, sent_to_email text, sent_subject text, sent_body text,"
        " inquiry_version_at_send integer,"
        " version integer NOT NULL DEFAULT 1,"
        " created_at timestamptz NOT NULL DEFAULT now(), created_by uuid NOT NULL,"
        " updated_at timestamptz NOT NULL DEFAULT now(),"
        " CONSTRAINT rfq_org_id_key UNIQUE (organization_id, id),"
        f" CONSTRAINT rfq_status_valid CHECK (status IN ({STATUSES})),"
        " CONSTRAINT rfq_sent_consistent CHECK"
        " (((status IN ('sent', 'declined')) = (sent_at IS NOT NULL AND sent_to_email IS NOT NULL"
        " AND sent_subject IS NOT NULL AND sent_body IS NOT NULL"
        " AND inquiry_version_at_send IS NOT NULL))"
        " AND (status IN ('sent', 'declined') OR (sent_at IS NULL AND sent_to_email IS NULL"
        " AND sent_subject IS NULL AND sent_body IS NULL AND inquiry_version_at_send IS NULL))),"
        " CONSTRAINT rfq_inquiry_fk FOREIGN KEY (organization_id, inquiry_id)"
        " REFERENCES inquiry (organization_id, id),"
        " CONSTRAINT rfq_counterparty_fk FOREIGN KEY (organization_id, counterparty_id)"
        " REFERENCES counterparty (organization_id, id),"
        " CONSTRAINT rfq_contact_fk FOREIGN KEY (organization_id, counterparty_id, contact_id)"
        " REFERENCES contact (organization_id, counterparty_id, id),"
        " CONSTRAINT rfq_created_by_fk FOREIGN KEY (organization_id, created_by)"
        " REFERENCES app_user (organization_id, id))"
    )
    op.execute(
        "CREATE UNIQUE INDEX rfq_one_active_idx ON rfq (inquiry_id, counterparty_id)"
        " WHERE status <> 'withdrawn'"
    )
    op.execute(
        "CREATE FUNCTION rfq_sent_immutable_fn() RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN"
        " IF OLD.sent_body IS NOT NULL AND (ROW(NEW.sent_at, NEW.sent_to_email, NEW.sent_subject,"
        " NEW.sent_body, NEW.inquiry_version_at_send)"
        " IS DISTINCT FROM ROW(OLD.sent_at, OLD.sent_to_email, OLD.sent_subject,"
        " OLD.sent_body, OLD.inquiry_version_at_send)) THEN"
        " RAISE EXCEPTION 'rfq_sent_immutable: sent snapshot of rfq % is frozen', OLD.id"
        " USING ERRCODE = 'integrity_constraint_violation';"
        " END IF;"
        " RETURN NEW; END; $$"
    )
    op.execute(
        "CREATE TRIGGER rfq_sent_immutable BEFORE UPDATE ON rfq"
        " FOR EACH ROW EXECUTE FUNCTION rfq_sent_immutable_fn()"
    )
    op.execute("ALTER TABLE rfq ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rfq FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY org_isolation ON rfq USING (organization_id = {ORG})"
        f" WITH CHECK (organization_id = {ORG})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON rfq TO nd_app")
    _set_actions(NEW_ACTIONS)


def downgrade() -> None:
    """Drop everything this revision created."""
    op.execute("DROP TABLE rfq")  # drops the trigger and index with it
    op.execute("DROP FUNCTION rfq_sent_immutable_fn()")
    # NOT VALID: audit rows with the new actions may exist and the log is append-only.
    _set_actions(OLD_ACTIONS, " NOT VALID")
    op.execute("ALTER TABLE contact DROP CONSTRAINT contact_org_cp_id_key")
    op.execute("ALTER TABLE inquiry DROP COLUMN rfq_deadline")
