"""Dev-only seed: the two demo organizations. Run as nd_owner (ND_SEED_DEV_DATA=true)."""

import os
import uuid

from sqlalchemy import Engine, create_engine, text

# Must match the `org_id` attributes of the users in infra/keycloak/realm-dev.json.
DEV_ORGS = {
    uuid.UUID("11111111-1111-4111-8111-111111111111"): "Acme Shipping",
    uuid.UUID("22222222-2222-4222-8222-222222222222"): "Borealis Tankers",
}


def seed_dev_orgs(engine: Engine) -> None:
    """Insert the demo organizations; safe to re-run."""
    with engine.begin() as conn:
        for org_id, name in DEV_ORGS.items():
            # FORCE RLS binds the owner too, so scope each insert to its organization.
            conn.execute(
                text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org_id)}
            )
            conn.execute(
                text(
                    "INSERT INTO organization (id, name) VALUES (:i, :n)"
                    " ON CONFLICT (id) DO NOTHING"
                ),
                {"i": org_id, "n": name},
            )


def main() -> None:
    """Seed using the owner URL from the environment."""
    seed_dev_orgs(create_engine(os.environ["ND_MIGRATION_DATABASE_URL"]))


if __name__ == "__main__":  # pragma: no cover
    main()
