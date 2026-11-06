"""Nomination table: versioned drafts to the winning supplier, frozen when sent.

Revision ID: 0006
Revises: 0005

The offer is the inquiry's offer by composite FK (organization_id, inquiry_id, offer_id).
"Contact belongs to the offer's counterparty" cannot be a composite FK because the offer does not
carry counterparty_id (it lives on the RFQ), so a trigger checks it. Denormalising counterparty_id
onto offer and nomination would touch B4's table for one rule. Whether the offer is the *current
winner* is an API rule (Task 3). Audit verbs are reused (create, update, send, withdraw), so the
audit action check is unchanged.
"""

from alembic import op

from nautical_deliverance.domain.nomination import NominationStatus

revision = "0006"
down_revision = "0005"

ORG = "nullif(current_setting('app.organization_id', true), '')::uuid"
STATUSES = ", ".join(f"'{s.value}'" for s in NominationStatus)
SENT_FIELDS = ("sent_at", "sent_to_email", "sent_subject", "sent_body", "inquiry_version_at_send")
ALL_SET = " AND ".join(f"{c} IS NOT NULL" for c in SENT_FIELDS)
ALL_NULL = " AND ".join(f"{c} IS NULL" for c in SENT_FIELDS)
NEW = ", ".join(f"NEW.{c}" for c in SENT_FIELDS)
OLD = ", ".join(f"OLD.{c}" for c in SENT_FIELDS)


def upgrade() -> None:
    """Create nomination, its guard triggers and RLS."""
    op.execute(  # target of the contact FK
        "ALTER TABLE contact ADD CONSTRAINT contact_org_id_key UNIQUE (organization_id, id)"
    )
    op.execute(
        "CREATE TABLE nomination (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        " organization_id uuid NOT NULL REFERENCES organization (id),"
        " inquiry_id uuid NOT NULL, offer_id uuid NOT NULL, contact_id uuid NOT NULL,"
        " status text NOT NULL DEFAULT 'draft', sequence integer,"
        " sent_at timestamptz, sent_to_email text, sent_subject text, sent_body text,"
        " inquiry_version_at_send integer,"
        " version integer NOT NULL DEFAULT 1,"
        " created_at timestamptz NOT NULL DEFAULT now(), created_by uuid NOT NULL,"
        " updated_at timestamptz NOT NULL DEFAULT now(),"
        " CONSTRAINT nomination_org_id_key UNIQUE (organization_id, id),"
        f" CONSTRAINT nomination_status_valid CHECK (status IN ({STATUSES})),"
        " CONSTRAINT nomination_sequence_positive CHECK (sequence > 0),"
        " CONSTRAINT nomination_sequence_consistent CHECK"
        " ((status = 'sent') = (sequence IS NOT NULL)),"
        " CONSTRAINT nomination_sent_consistent CHECK"
        f" (((status = 'sent') = ({ALL_SET}))"
        f" AND (status = 'sent' OR ({ALL_NULL}))),"
        " CONSTRAINT nomination_inquiry_fk FOREIGN KEY (organization_id, inquiry_id)"
        " REFERENCES inquiry (organization_id, id),"
        " CONSTRAINT nomination_offer_fk FOREIGN KEY (organization_id, inquiry_id, offer_id)"
        " REFERENCES offer (organization_id, inquiry_id, id),"
        " CONSTRAINT nomination_contact_fk FOREIGN KEY (organization_id, contact_id)"
        " REFERENCES contact (organization_id, id),"
        " CONSTRAINT nomination_created_by_fk FOREIGN KEY (organization_id, created_by)"
        " REFERENCES app_user (organization_id, id))"
    )
    op.execute(
        "CREATE UNIQUE INDEX nomination_one_draft_idx ON nomination (inquiry_id)"
        " WHERE status = 'draft'"
    )
    op.execute(
        "CREATE UNIQUE INDEX nomination_sequence_idx ON nomination (inquiry_id, sequence)"
        " WHERE status = 'sent'"
    )
    # AFTER trigger below: FK and RLS checks report their own, clearer errors first.
    op.execute(
        "CREATE FUNCTION nomination_contact_fn() RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN"
        " IF NOT EXISTS (SELECT 1 FROM offer o JOIN rfq r ON r.id = o.rfq_id"
        " JOIN contact c ON c.counterparty_id = r.counterparty_id"
        " WHERE o.id = NEW.offer_id AND c.id = NEW.contact_id) THEN"
        " RAISE EXCEPTION 'nomination_contact_counterparty: contact must belong to the"
        " counterparty of the offer' USING ERRCODE = 'integrity_constraint_violation';"
        " END IF;"
        " RETURN NEW; END; $$"
    )
    op.execute(
        "CREATE TRIGGER nomination_contact_counterparty"
        " AFTER INSERT OR UPDATE OF contact_id, offer_id ON nomination"
        " FOR EACH ROW EXECUTE FUNCTION nomination_contact_fn()"
    )
    op.execute(
        "CREATE FUNCTION nomination_sent_immutable_fn() RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN"
        f" IF OLD.sent_body IS NOT NULL AND (ROW({NEW}, NEW.sequence)"
        f" IS DISTINCT FROM ROW({OLD}, OLD.sequence)) THEN"
        " RAISE EXCEPTION 'nomination_sent_immutable: sent snapshot of nomination % is frozen',"
        " OLD.id USING ERRCODE = 'integrity_constraint_violation';"
        " END IF;"
        " RETURN NEW; END; $$"
    )
    op.execute(
        "CREATE TRIGGER nomination_sent_immutable BEFORE UPDATE ON nomination"
        " FOR EACH ROW EXECUTE FUNCTION nomination_sent_immutable_fn()"
    )
    op.execute("ALTER TABLE nomination ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE nomination FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY org_isolation ON nomination USING (organization_id = {ORG})"
        f" WITH CHECK (organization_id = {ORG})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON nomination TO nd_app")


def downgrade() -> None:
    """Drop everything this revision created (audit check was not widened)."""
    op.execute("DROP TABLE nomination")  # drops triggers and indexes with it
    op.execute("DROP FUNCTION nomination_contact_fn()")
    op.execute("DROP FUNCTION nomination_sent_immutable_fn()")
    op.execute("ALTER TABLE contact DROP CONSTRAINT contact_org_id_key")
