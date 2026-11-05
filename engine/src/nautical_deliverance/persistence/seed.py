"""Dev-only seed: the two demo organizations and their demo master data (B1-R10, D-066).

Run as nd_owner (ND_SEED_DEV_DATA=true). Everything is idempotent (natural-key
``ON CONFLICT DO NOTHING`` / ``WHERE NOT EXISTS``): a second run changes no row.

Demo data only: ports are real public data; companies, vessels and people are invented and
e-mails use the reserved ``.example`` TLD and phones
are Ofcom's drama range (+44 20 7946 0000-0999). No audit entries are written: this is
bootstrap data
that exists before any actor does, and the audit log records only user-driven changes (B1-D12).

IMO numbers are synthetic: chosen only to satisfy the check digit, they may coincide with real
ships. All company, vessel and person names are invented (checked against well-known shipping
and bunker companies).

Sources, retrieved 2026-11-05:
* UN/LOCODE: every port code below was checked as present with the port function flag (1) in
  https://github.com/datasets/un-locode (data/code-list.csv, a mirror of the UNECE UN/LOCODE
  list; service.unece.org itself answered 403 to the automated fetch). Shanghai is CNSGH, not
  CNSHA (CNSHA is an airport), which is why it is not used.
* IANA tz database: zones are asserted loadable by ``zoneinfo`` (tzdata) in
  tests/db/test_seed_master.py.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.orm import Session

from nautical_deliverance.persistence.inquiry_repo import next_reference

# Must match the `org_id` attributes of the users in infra/keycloak/realm-dev.json.
DEV_ORGS = {
    uuid.UUID("11111111-1111-4111-8111-111111111111"): "Acme Shipping",
    uuid.UUID("22222222-2222-4222-8222-222222222222"): "Borealis Tankers",
}

# Must match `id`, `org_id`, names, e-mails and roles of infra/keycloak/realm-dev.json (the id is
# the Keycloak `sub`, so a user's first login upserts onto the seeded row).
DEV_USERS = tuple(
    (uuid.UUID(f"{c * 8}-0000-4000-8000-{n:012d}"), org, name, f"{role}@{dom}", role)
    for c, org, dom, people in (
        ("a", uuid.UUID("11111111-1111-4111-8111-111111111111"), "acme.test",
         ("Ada Admin", "Bea Buyer", "Olle Operator", "Vera Viewer")),
        ("b", uuid.UUID("22222222-2222-4222-8222-222222222222"), "borealis.test",
         ("Alma Admin", "Bo Buyer", "Otto Operator", "Vide Viewer")),
    )
    for n, (role, name) in enumerate(
        zip(("admin", "bunker_buyer", "operator", "viewer"), people, strict=True), 1
    )
)  # fmt: skip

PRODUCTS = (  # name, default unit (spec §3.1, per the brief)
    ("HSFO 3.5%", "mt"), ("VLSFO 0.5%", "mt"), ("DMA 0.1%", "mt"), ("Biofuel", "mt"),
    ("B24", "mt"), ("B30", "mt"), ("B100", "mt"), ("Bio diesel FAME", "mt"),
)  # fmt: skip
ISO = ("ISO 8217:2005", "ISO 8217:2010", "ISO 8217:2012", "ISO 8217:2017", "ISO 8217:2024")
REASONS = ("Bunkers only", "Working cargo", "Debunkering")
PORTS = (  # locode, name, country, IANA zone
    ("NLRTM", "Rotterdam", "NL", "Europe/Amsterdam"),
    ("SGSIN", "Singapore", "SG", "Asia/Singapore"),
    ("GIGIB", "Gibraltar", "GI", "Europe/Gibraltar"),
    ("USHOU", "Houston", "US", "America/Chicago"),
    ("AEFJR", "Fujairah", "AE", "Asia/Dubai"),
    ("BEANR", "Antwerp", "BE", "Europe/Brussels"),
    ("ESALG", "Algeciras", "ES", "Europe/Madrid"),
    ("KRPUS", "Busan", "KR", "Asia/Seoul"),
    ("GRPIR", "Piraeus", "GR", "Europe/Athens"),
    ("MTMAR", "Marsaxlokk", "MT", "Europe/Malta"),
    ("BRSSZ", "Santos", "BR", "America/Sao_Paulo"),
    ("ZADUR", "Durban", "ZA", "Africa/Johannesburg"),
)
_CONV = ("VLSFO 0.5%", "HSFO 3.5%", "DMA 0.1%")
_BIO = (*_CONV, "B24", "B30", "Biofuel")

# Per organization: legal entities (code, name); vessels (name, imo, type, dwt, flag, entity
# code, approved fuels); counterparties (name, type, notes, contacts, coverage {port: products}).
# The first contact of a counterparty is its primary one.
ORG_DATA: dict[uuid.UUID, dict[str, Any]] = {
    uuid.UUID("11111111-1111-4111-8111-111111111111"): {
        "entities": (("AMH", "Acme Maritime Holdings Ltd"), ("ATS", "Acme Tankers Singapore Pte")),
        "vessels": (
            ("Acme Aurora", "9391012", "Aframax tanker", 115000, "MH", "AMH", _BIO),
            ("Acme Meridian", "9391024", "Suezmax tanker", 158000, "SG", "ATS", _BIO),
            ("Acme Polaris", "9391036", "Panamax bulk carrier", 82000, "MT", "AMH", _CONV),
            ("Acme Horizon", "9391048", "Container ship", 98000, "LR", "AMH", _CONV),
            ("Acme Tern", "9391050", "Product tanker", 50000, "SG", "ATS", _CONV),
            ("Acme Vega", "9391062", "Capesize bulk carrier", 180000, "MH", "AMH", _BIO),
        ),
        "counterparties": (
            (
                "Alpha Fuels",
                "physical_supplier",
                "Barge fleet in ARA and Antwerp.",
                (("Anna Verhoeven", "anna.verhoeven@alphafuels.example", "+44 20 7946 0101"),),
                dict.fromkeys(("NLRTM", "BEANR"), _BIO),
            ),
            (
                "Bravo Marine Energy",
                "physical_supplier",
                "Strong in Singapore and Busan.",
                (
                    ("Ben Tan", "ben.tan@bravomarine.example", None),
                    ("Mei Lim", "mei.lim@bravomarine.example", "+44 20 7946 0102"),
                ),
                {"SGSIN": _BIO, "KRPUS": _CONV},
            ),
            (
                "Charlie Bunkers",
                "physical_supplier",
                "Gibraltar and Algeciras stems.",
                (("Carlos Ruiz", "carlos.ruiz@charliebunkers.example", None),),
                {"GIGIB": _CONV, "ESALG": ("VLSFO 0.5%", "DMA 0.1%")},
            ),
            (
                "Delta Energy Trading",
                "trader",
                "Trader; physical supplier relationship: Alpha Fuels (RTM), Bravo (SIN).",
                (("Dana Olsen", "dana.olsen@deltatrading.example", None),),
                {
                    "NLRTM": ("VLSFO 0.5%", "DMA 0.1%", "HSFO 3.5%"),
                    "SGSIN": ("VLSFO 0.5%", "DMA 0.1%"),
                    "USHOU": ("VLSFO 0.5%", "DMA 0.1%"),
                },
            ),
            (
                "Echo Oil Brokers",
                "trader",
                "Broker; sources from local barge operators.",
                (("Eva Lindqvist", "eva.lindqvist@echobrokers.example", None),),
                {
                    "AEFJR": ("VLSFO 0.5%", "HSFO 3.5%"),
                    "GRPIR": ("VLSFO 0.5%",),
                    "MTMAR": ("DMA 0.1%",),
                },
            ),
            (
                "Foxtrot Petroleum",
                "both",
                "Own barges in Fujairah, trades elsewhere.",
                (
                    ("Farid Haddad", "farid.haddad@foxtrotpetroleum.example", "+44 20 7946 0103"),
                    ("Fatima Noor", "fatima.noor@foxtrotpetroleum.example", None),
                ),
                {
                    "AEFJR": _BIO,
                    "NLRTM": ("VLSFO 0.5%", "DMA 0.1%", "B30"),
                    "ZADUR": ("VLSFO 0.5%", "DMA 0.1%"),
                },
            ),
            (
                "Golf Gulf Supply",
                "physical_supplier",
                "Texas Gulf coast.",
                (("Grace Miller", "grace.miller@golfgulf.example", None),),
                {"USHOU": _CONV, "BRSSZ": ("VLSFO 0.5%", "DMA 0.1%")},
            ),
            (
                "Hotel Harbour Fuels",
                "both",
                "Mediterranean hub; Biofuel blends on request.",
                (("Hugo Costa", "hugo.costa@hotelharbour.example", None),),
                {"GRPIR": _BIO, "MTMAR": _CONV, "GIGIB": ("VLSFO 0.5%", "DMA 0.1%", "B30")},
            ),
        ),
    },
    uuid.UUID("22222222-2222-4222-8222-222222222222"): {
        "entities": (("BMA", "Borealis Marine AS"), ("BGC", "Borealis Gas Carriers Ltd")),
        "vessels": (
            ("Borealis Fjord", "9402017", "LR2 tanker", 110000, "NO", "BMA", _BIO),
            ("Borealis Saga", "9402029", "MR tanker", 49000, "NO", "BMA", _CONV),
            ("Borealis Nord", "9402031", "VLCC", 300000, "MH", "BMA", _BIO),
            (
                "Borealis Ymir",
                "9402043",
                "LNG carrier",
                85000,
                "GB",
                "BGC",
                ("DMA 0.1%", "HSFO 3.5%"),
            ),
            ("Borealis Skarv", "9402055", "Chemical tanker", 40000, "NO", "BMA", _CONV),
            (
                "Borealis Rune",
                "9402067",
                "Ro-ro cargo",
                20000,
                "SE",
                "BMA",
                ("VLSFO 0.5%", "DMA 0.1%"),
            ),
        ),
        "counterparties": (
            (
                "November Bunkers",
                "physical_supplier",
                "ARA barging.",
                (("Nils Aaberg", "nils.aaberg@novemberbunkers.example", None),),
                dict.fromkeys(("NLRTM", "BEANR"), _BIO),
            ),
            (
                "Oscar Marine Fuels",
                "physical_supplier",
                "Mediterranean and Gibraltar.",
                (("Olivia Perez", "olivia.perez@oscarfuels.example", None),),
                {"ESALG": _CONV, "GIGIB": _CONV, "MTMAR": ("VLSFO 0.5%", "DMA 0.1%")},
            ),
            (
                "Papa Supply Co",
                "physical_supplier",
                "Singapore and Busan.",
                (
                    ("Peter Wong", "peter.wong@papasupply.example", None),
                    ("Priya Nair", "priya.nair@papasupply.example", None),
                ),
                {"SGSIN": _BIO, "KRPUS": ("VLSFO 0.5%", "DMA 0.1%")},
            ),
            (
                "Quebec Trading",
                "trader",
                "Trader; physical supplier relationship: November Bunkers, Oscar.",
                (("Quentin Berg", "quentin.berg@quebectrading.example", None),),
                {
                    "NLRTM": ("VLSFO 0.5%", "DMA 0.1%", "HSFO 3.5%"),
                    "GIGIB": ("VLSFO 0.5%", "DMA 0.1%"),
                },
            ),
            (
                "Romeo Energy Partners",
                "trader",
                "Global trader, strong in the Gulf.",
                (("Rania Saleh", "rania.saleh@romeoenergy.example", None),),
                {
                    "AEFJR": ("VLSFO 0.5%", "HSFO 3.5%", "DMA 0.1%"),
                    "USHOU": ("VLSFO 0.5%",),
                    "SGSIN": ("VLSFO 0.5%", "DMA 0.1%"),
                },
            ),
            (
                "Sierra Oil",
                "both",
                "Own storage in Piraeus.",
                (("Sofia Papas", "sofia.papas@sierraoil.example", "+44 20 7946 0104"),),
                {"GRPIR": _BIO, "MTMAR": _CONV},
            ),
            (
                "Tango Fuel Services",
                "physical_supplier",
                "Houston and Santos.",
                (("Tom Hargrove", "tom.hargrove@tangofuel.example", None),),
                {"USHOU": _CONV, "BRSSZ": ("VLSFO 0.5%", "DMA 0.1%", "HSFO 3.5%")},
            ),
            (
                "Uniform Bunkering",
                "both",
                "South Africa and Fujairah.",
                (("Uma Naidoo", "uma.naidoo@uniformbunkering.example", None),),
                {"ZADUR": _CONV, "AEFJR": ("VLSFO 0.5%", "DMA 0.1%")},
            ),
        ),
    },
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


class _Org:
    """Statements scoped to one organization (the RLS scope is already set on the connection)."""

    def __init__(self, conn: Connection, org: uuid.UUID) -> None:
        self.conn, self.org = conn, org

    def put(self, sql: str, **kw: object) -> None:
        self.conn.execute(text(sql), {"o": self.org, **kw})

    def one(self, sql: str, **kw: object) -> uuid.UUID:
        return cast("uuid.UUID", self.conn.execute(text(sql), {"o": self.org, **kw}).scalar_one())


def _seed_reference(db: _Org, d: dict[str, Any]) -> None:
    """Products, ISO versions, reasons, ports, legal entities."""
    for name, unit in PRODUCTS:
        db.put(
            "INSERT INTO product (organization_id, name, default_unit) VALUES (:o, :n, :u)"
            " ON CONFLICT DO NOTHING",
            n=name,
            u=unit,
        )
    for name in ISO:
        db.put(
            "INSERT INTO iso_spec_version (organization_id, name) VALUES (:o, :n)"
            " ON CONFLICT DO NOTHING",
            n=name,
        )
    for name in REASONS:
        db.put(
            "INSERT INTO bunkering_reason (organization_id, name) VALUES (:o, :n)"
            " ON CONFLICT DO NOTHING",
            n=name,
        )
    for locode, name, country, tz in PORTS:
        db.put(
            "INSERT INTO port (organization_id, locode, name, country, time_zone)"
            " VALUES (:o, :l, :n, :c, :t) ON CONFLICT DO NOTHING",
            l=locode,
            n=name,
            c=country,
            t=tz,
        )
    for code, name in d["entities"]:
        db.put(
            "INSERT INTO legal_entity (organization_id, code, name) VALUES (:o, :c, :n)"
            " ON CONFLICT DO NOTHING",
            c=code,
            n=name,
        )


def _product(db: _Org, name: str) -> uuid.UUID:
    return db.one("SELECT id FROM product WHERE name = :n", n=name)


def _seed_vessels(db: _Org, d: dict[str, Any]) -> None:
    for name, imo, vtype, dwt, flag, entity, fuels in d["vessels"]:
        db.put(
            "INSERT INTO vessel (organization_id, name, imo, vessel_type, dwt, flag,"
            " legal_entity_id) VALUES (:o, :n, :i, :t, :d, :f,"
            " (SELECT id FROM legal_entity WHERE code = :e)) ON CONFLICT DO NOTHING",
            n=name,
            i=imo,
            t=vtype,
            d=dwt,
            f=flag,
            e=entity,
        )
        vid = db.one("SELECT id FROM vessel WHERE imo = :i", i=imo)
        for fuel in fuels:
            db.put(
                "INSERT INTO vessel_approved_fuel (organization_id, vessel_id, product_id)"
                " VALUES (:o, :v, :p) ON CONFLICT DO NOTHING",
                v=vid,
                p=_product(db, fuel),
            )


def _seed_counterparties(db: _Org, d: dict[str, Any]) -> None:
    for name, ctype, notes, contacts, coverage in d["counterparties"]:
        db.put(  # no natural-key constraint on counterparty, so guard by name
            "INSERT INTO counterparty (organization_id, name, type, notes)"
            " SELECT :o, :n, :t, :x WHERE NOT EXISTS (SELECT 1 FROM counterparty WHERE name = :n)",
            n=name,
            t=ctype,
            x=notes,
        )
        cid = db.one("SELECT id FROM counterparty WHERE name = :n", n=name)
        for i, (cname, email, phone) in enumerate(contacts):
            db.put(
                "INSERT INTO contact (organization_id, counterparty_id, name, email, phone,"
                " is_primary) SELECT :o, :c, :n, :e, :p, :pr WHERE NOT EXISTS"
                " (SELECT 1 FROM contact WHERE counterparty_id = :c AND email = :e)",
                c=cid,
                n=cname,
                e=email,
                p=phone,
                pr=i == 0,
            )
        for locode, products in coverage.items():
            port_id = db.one("SELECT id FROM port WHERE locode = :l", l=locode)
            for p in products:
                db.put(
                    "INSERT INTO coverage (organization_id, counterparty_id, port_id, product_id)"
                    " VALUES (:o, :c, :pt, :pr) ON CONFLICT DO NOTHING",
                    c=cid,
                    pt=port_id,
                    pr=_product(db, p),
                )


def seed_demo_master(engine: Engine) -> None:
    """Insert each dev organization's own demo master data; safe to re-run."""
    with engine.begin() as conn:
        for org, data in ORG_DATA.items():
            conn.execute(
                text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)}
            )
            db = _Org(conn, org)
            _seed_reference(db, data)
            _seed_vessels(db, data)
            _seed_counterparties(db, data)


def _scope(conn: Connection, org: uuid.UUID) -> _Org:
    conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
    return _Org(conn, org)


def seed_demo_users(engine: Engine, now: datetime | None = None) -> None:
    """Insert the realm users, refreshing name, e-mail and roles; safe to re-run."""
    now = now or datetime.now(UTC)
    with engine.begin() as conn:
        for uid, org, name, email, role in DEV_USERS:
            _scope(conn, org).put(
                "INSERT INTO app_user (id, organization_id, last_seen_at, name, email, roles)"
                " VALUES (:i, :o, :t, :n, :e, :r) ON CONFLICT (id) DO UPDATE"
                " SET name = :n, email = :e, roles = :r"
                " WHERE (app_user.name, app_user.email, app_user.roles)"
                " IS DISTINCT FROM (:n, :e, :r)",
                i=uid,
                t=now,
                n=name,
                e=email,
                r=[role],
            )


# Demo inquiries per organization: (status, buyer?, vessel pick, port, reason, ETA hours from
# the seed time, stay hours, lines (product, qty, unit, density), cancel reason). "bio_less" is
# the first vessel without B24 approval (so B24 triggers the not-approved-fuel warning).
_ISO = "ISO 8217:2024"
_VL, _DMA = "VLSFO 0.5%", "DMA 0.1%"
_INQUIRIES = (
    ("draft", False, 0, "NLRTM", "Bunkers only", 30, 20, ((_VL, "500", "mt", None),), None),
    ("draft", True, 1, "SGSIN", "Bunkers only", 120, 30,
     ((_DMA, "120.5", "m3", "850.0"), (_VL, "800", "mt", None)), None),
    ("draft", True, "bio_less", "GIGIB", "Working cargo", 150, 24,
     (("B24", "300", "mt", None),), None),
    ("rfq_sent", True, 3, "AEFJR", "Bunkers only", 72, 36,
     (("HSFO 3.5%", "1200", "mt", None),), None),
    ("offers_received", True, 4, "GRPIR", "Debunkering", 96, 28, ((_VL, "650", "mt", None),), None),
    ("nominated", True, 5, "USHOU", "Bunkers only", 200, 40,
     ((_VL, "900", "mt", None), (_DMA, "100", "mt", None)), None),
    ("cancelled", True, 0, "BEANR", "Working cargo", 60, 24,
     ((_DMA, "250", "mt", None),), "Voyage cancelled by charterer"),
)  # fmt: skip


def _seed_inquiry(  # noqa: PLR0913, PLR0917
    db: _Org,
    s: Session,
    now: datetime,
    n: int,
    spec: tuple[Any, ...],
    vessels: tuple[Any, ...],
    users: dict[str, uuid.UUID],
) -> None:
    status, buyer, pick, port, reason, eta_h, stay_h, lines, cancel = spec
    voyage = f"DEMO-{n}"  # marker: a present voyage means this inquiry was already seeded
    if db.conn.execute(text("SELECT 1 FROM inquiry WHERE voyage = :v"), {"v": voyage}).first():
        return
    vessel = next(v for v in vessels if "B24" not in v[6]) if pick == "bio_less" else vessels[pick]
    iid = db.one(
        "INSERT INTO inquiry (organization_id, reference, status, vessel_id, legal_entity_id,"
        " port_id, bunkering_reason_id, voyage, operator_id, requester_id, buyer_id, eta, etd,"
        " cancel_reason, created_by, created_at, updated_at) VALUES (:o, :ref, :st,"
        " (SELECT id FROM vessel WHERE imo = :imo),"
        " (SELECT id FROM legal_entity WHERE code = :le), (SELECT id FROM port WHERE locode = :lc),"
        " (SELECT id FROM bunkering_reason WHERE name = :br), :v, :op, :op, :by, :eta, :etd,"
        " :cr, :op, :now, :now) RETURNING id",
        ref=next_reference(s, db.org, now),
        st=status,
        imo=vessel[1],
        le=vessel[5],
        lc=port,
        br=reason,
        v=voyage,
        op=users["operator"],
        by=users["bunker_buyer"] if buyer else None,
        eta=now + timedelta(hours=eta_h),
        etd=now + timedelta(hours=eta_h + stay_h),
        cr=cancel,
        now=now,
    )
    for pos, (product, qty, unit, density) in enumerate(lines, 1):
        db.put(
            "INSERT INTO inquiry_line (organization_id, inquiry_id, position, product_id,"
            " quantity, unit, density, iso_spec_version_id) VALUES (:o, :i, :p,"
            " (SELECT id FROM product WHERE name = :pr), :q, :u, :d,"
            " (SELECT id FROM iso_spec_version WHERE name = :iso))",
            i=iid, p=pos, pr=product, q=qty, u=unit, d=density, iso=_ISO,
        )  # fmt: skip


def seed_demo_inquiries(engine: Engine, now: datetime | None = None) -> None:
    """Insert demo users and each organization's demo inquiries (ETAs relative to ``now``).

    Needs seed_demo_master first. Non-draft statuses are written directly (no transition API
    yet). Like the master seed this writes no audit entries (B1-D12); safe to re-run.
    """
    now = now or datetime.now(UTC)
    seed_demo_users(engine, now)
    with engine.begin() as conn:
        for org, data in ORG_DATA.items():
            db = _scope(conn, org)
            users = {role: uid for uid, o, _n, _e, role in DEV_USERS if o == org}
            s = Session(conn)
            for n, spec in enumerate(_INQUIRIES, 1):
                _seed_inquiry(db, s, now, n, spec, data["vessels"], users)


def main() -> None:
    """Seed using the owner URL from the environment."""
    engine = create_engine(os.environ["ND_MIGRATION_DATABASE_URL"])
    seed_dev_orgs(engine)
    seed_demo_master(engine)
    seed_demo_inquiries(engine)


if __name__ == "__main__":  # pragma: no cover
    main()
