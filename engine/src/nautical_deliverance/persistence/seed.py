"""Demo seed and demo master data (B1-R10, D-066, B6-R04).

ND_SEED=dev seeds the two dev organizations, ND_SEED=pilot seeds Pilot Demo Shipping.

Run as nd_owner (ND_SEED=dev|pilot). Everything is idempotent (natural-key
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
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import Connection, Engine, create_engine, select, text
from sqlalchemy.orm import Session

from nautical_deliverance.domain.nomination import render_nomination
from nautical_deliverance.domain.offer import evaluate_offer
from nautical_deliverance.domain.rfq import render_rfq
from nautical_deliverance.persistence import nomination_repo, offer_repo
from nautical_deliverance.persistence.inquiry_repo import next_reference
from nautical_deliverance.persistence.models import Inquiry, Nomination, Offer, OfferLine, Rfq
from nautical_deliverance.persistence.rfq_repo import build_context

# Must match the `org_id` attributes of the users in infra/keycloak/realm-dev.json.
DEV_ORGS = {
    uuid.UUID("11111111-1111-4111-8111-111111111111"): "Acme Shipping",
    uuid.UUID("22222222-2222-4222-8222-222222222222"): "Borealis Tankers",
}

ACME = uuid.UUID("11111111-1111-4111-8111-111111111111")
BOREALIS = uuid.UUID("22222222-2222-4222-8222-222222222222")
# The pilot organization (B6-R04). The pilot realm has no users, so the demo inquiries are owned
# by PILOT_USERS, demo directory rows that are not in Keycloak (R3); real users arrive via /me.
PILOT_ORGS = {uuid.UUID("33333333-3333-4333-8333-333333333333"): "Pilot Demo Shipping"}


def _users(prefix: str, org: uuid.UUID, domain: str, people: tuple[str, ...]) -> tuple[Any, ...]:
    """(id, org, name, e-mail, role) per person; ids are ``prefix`` x8 + a running number."""
    return tuple(
        (uuid.UUID(f"{prefix * 8}-0000-4000-8000-{n:012d}"), org, name, f"{role}@{domain}", role)
        for n, (role, name) in enumerate(
            zip(("admin", "bunker_buyer", "operator", "viewer"), people, strict=True), 1
        )
    )


# Must match `id`, `org_id`, names, e-mails and roles of infra/keycloak/realm-dev.json (the id is
# the Keycloak `sub`, so a user's first login upserts onto the seeded row).
DEV_USERS = (
    *_users("a", ACME, "acme.test", ("Ada Admin", "Bea Buyer", "Olle Operator", "Vera Viewer")),
    *_users(
        "b", BOREALIS, "borealis.test", ("Alma Admin", "Bo Buyer", "Otto Operator", "Vide Viewer")
    ),
)
PILOT_USERS = _users(
    "c", next(iter(PILOT_ORGS)), "pilot-demo.example",
    ("Pia Pilot (demo)", "Bruno Buyer (demo)", "Ola Operator (demo)", "Vilma Viewer (demo)"),
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


def _imo(base: int) -> str:
    """Return a synthetic IMO number: six digits plus the check digit (weights 7..2)."""
    return f"{base}{sum(int(d) * w for d, w in zip(str(base), range(7, 1, -1), strict=True)) % 10}"


def _pilot_data() -> dict[str, Any]:
    """Acme's counterparties and fleet shape under the pilot's own invented names (B6-D6)."""
    acme = ORG_DATA[ACME]
    entities = (("PDL", "Pilot Demo Shipping Ltd"), ("PDS", "Pilot Demo Singapore Pte"))
    codes = {old: new for (old, _), (new, _) in zip(acme["entities"], entities, strict=True)}
    names = (
        "Demo Aurora",
        "Demo Meridian",
        "Demo Polaris",
        "Demo Horizon",
        "Demo Tern",
        "Demo Vega",
    )
    vessels = tuple(
        (name, _imo(947300 + i), *v[2:5], codes[v[5]], v[6])
        for i, (name, v) in enumerate(zip(names, acme["vessels"], strict=True))
    )
    return {**acme, "entities": entities, "vessels": vessels}


ORG_DATA[next(iter(PILOT_ORGS))] = _pilot_data()


def seed_orgs(engine: Engine, orgs: dict[uuid.UUID, str] = DEV_ORGS) -> None:
    """Insert the demo organizations (the dev ones by default); safe to re-run."""
    with engine.begin() as conn:
        for org_id, name in orgs.items():
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


def seed_demo_master(engine: Engine, orgs: tuple[uuid.UUID, ...] = tuple(DEV_ORGS)) -> None:
    """Insert each organization's own demo master data; safe to re-run."""
    with engine.begin() as conn:
        for org in orgs:
            data = ORG_DATA[org]
            db = _scope(conn, org)
            _seed_reference(db, data)
            _seed_vessels(db, data)
            _seed_counterparties(db, data)


def _scope(conn: Connection, org: uuid.UUID) -> _Org:
    conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
    return _Org(conn, org)


def seed_demo_users(
    engine: Engine, now: datetime | None = None, users: tuple[Any, ...] = DEV_USERS
) -> None:
    """Insert the realm (or pilot demo) users, refreshing name, e-mail, roles; safe to re-run."""
    now = now or datetime.now(UTC)
    with engine.begin() as conn:
        for uid, org, name, email, role in users:
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
    ("rfq_sent", True, 3, "AEFJR", "Bunkers only", 40, 36,
     (("HSFO 3.5%", "1200", "mt", None),), None),
    ("offers_received", True, 4, "GRPIR", "Debunkering", 96, 28, ((_VL, "650", "mt", None),), None),
    ("nominated", True, 5, "USHOU", "Bunkers only", 200, 40,
     ((_VL, "900", "mt", None), (_DMA, "100", "mt", None)), None),
    ("cancelled", True, 0, "BEANR", "Working cargo", 60, 24,
     ((_DMA, "250", "mt", None),), "Voyage cancelled by charterer"),
    ("winner_selected", True, 2, "NLRTM", "Bunkers only", 100, 30,
     ((_VL, "700", "mt", None), (_DMA, "150", "mt", None)), None),
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


def seed_demo_inquiries(engine: Engine, now: datetime | None = None, mode: str = "dev") -> None:
    """Insert demo users, inquiries and RFQs per organization (ETAs relative to ``now``).

    Needs seed_demo_master first. Non-draft statuses are written directly (no transition API
    yet). Like the master seed this writes no audit entries (B1-D12); safe to re-run.
    """
    now = now or datetime.now(UTC)
    people = PILOT_USERS if mode == "pilot" else DEV_USERS
    seed_demo_users(engine, now, people)
    with engine.begin() as conn:
        for org in dict.fromkeys(o for _i, o, *_r in people):
            data = ORG_DATA[org]
            db = _scope(conn, org)
            users = {role: uid for uid, o, _n, _e, role in people if o == org}
            s = Session(conn)
            for n, spec in enumerate(_INQUIRIES, 1):
                _seed_inquiry(db, s, now, n, spec, data["vessels"], users)
            _seed_rfqs(db, s, now, users)
            _seed_offers(db, s, now, users)
            _seed_nominations(db, s, now, users)


# Demo RFQs by inquiry voyage marker: the final status of each RFQ, one per recipient.
_RFQS = {
    "DEMO-2": ("draft", "draft"),
    "DEMO-4": ("sent", "sent"),
    "DEMO-5": ("sent", "declined"),
    "DEMO-6": ("sent",),
    "DEMO-8": ("sent", "sent", "sent", "sent"),
}


def _seed_rfqs(db: _Org, s: Session, now: datetime, users: dict[str, uuid.UUID]) -> None:
    """Add the demo RFQs; recipients are covering counterparties first, with a primary contact."""
    for voyage, statuses in _RFQS.items():
        row = db.conn.execute(
            text(
                # The oldest inquiry with the marker is the seeded one: Duplicate copies the voyage.
                "SELECT id, port_id, version, eta FROM inquiry WHERE voyage = :v"
                " ORDER BY created_at, reference LIMIT 1"
            ),
            {"v": voyage},
        ).one()
        if db.conn.execute(text("SELECT 1 FROM rfq WHERE inquiry_id = :i"), {"i": row.id}).first():
            continue
        recipients = db.conn.execute(
            text(
                "SELECT cp.id AS cp, ct.id AS contact FROM counterparty cp"
                " JOIN contact ct ON ct.counterparty_id = cp.id AND ct.is_primary"
                " WHERE cp.active AND ct.active ORDER BY EXISTS (SELECT 1 FROM coverage c"
                " WHERE c.counterparty_id = cp.id AND c.port_id = :p) DESC, cp.name LIMIT :n"
            ),
            {"p": row.port_id, "n": len(statuses)},
        ).all()
        for (cp, contact), status in zip(recipients, statuses, strict=True):
            rfq = Rfq(
                id=uuid.uuid4(), organization_id=db.org, inquiry_id=row.id, counterparty_id=cp,
                contact_id=contact, status=status, response_deadline=row.eta - timedelta(hours=24),
                generated_at=now, created_at=now, created_by=users["bunker_buyer"], updated_at=now,
                version=1,
            )  # fmt: skip
            if status != "draft":  # frozen exactly as the send action would
                ctx = build_context(s, rfq)
                rfq.sent_subject, rfq.sent_body = render_rfq(ctx)
                rfq.sent_at, rfq.sent_to_email = now, ctx.recipient_email
                rfq.inquiry_version_at_send = row.version
            s.add(rfq)
        s.flush()


# Demo offers by inquiry voyage marker, one per sent RFQ in counterparty-name order:
# (hours until valid_until, USD/mt per inquiry line or None for a missing line, barging cost).
_OFFERS = {
    "DEMO-5": ((48, ("640",), "3500"),),
    "DEMO-6": ((72, ("655", "840"), "4200"),),
    "DEMO-8": (
        (72, ("640", "810"), "4500"),  # complete, lowest among those still selectable
        (20, ("665", "790"), "3000"),  # complete, dearer: the winner, ends inside 24 h
        (48, ("655", None), "0"),  # partial
        (-6, ("630", "800"), "0"),  # complete and cheapest, but expired
    ),
}
_WINNERS = {  # voyage -> (offer index, reason, note); a lowest offer needs no rationale
    "DEMO-6": (0, None, None),
    "DEMO-8": (1, "operational_fit", "Closer barge slot to the vessel's ETA."),
}


def _seed_offers(db: _Org, s: Session, now: datetime, users: dict[str, uuid.UUID]) -> None:
    """Attach offers to the sent demo RFQs and record the one decision (totals via the domain)."""
    buyer = users["bunker_buyer"]
    for voyage, specs in _OFFERS.items():
        inq = db.conn.execute(
            text("SELECT id FROM inquiry WHERE voyage = :v ORDER BY created_at, reference LIMIT 1"),
            {"v": voyage},
        ).scalar_one()
        if db.conn.execute(text("SELECT 1 FROM offer WHERE inquiry_id = :i"), {"i": inq}).first():
            continue
        rfq_ids = (
            db.conn.execute(
                text(
                    "SELECT r.id FROM rfq r JOIN counterparty c ON c.id = r.counterparty_id"
                    " WHERE r.inquiry_id = :i AND r.status = 'sent' ORDER BY c.name"
                ),
                {"i": inq},
            )
            .scalars()
            .all()
        )
        line_ids = (
            db.conn.execute(
                text("SELECT id FROM inquiry_line WHERE inquiry_id = :i ORDER BY position"),
                {"i": inq},
            )
            .scalars()
            .all()
        )
        offers: list[Offer] = []
        for rfq_id, (hours, prices, barging) in zip(rfq_ids, specs, strict=True):
            offer = Offer(
                id=uuid.uuid4(), organization_id=db.org, rfq_id=rfq_id, inquiry_id=inq,
                valid_until=now + timedelta(hours=hours), barging_cost=Decimal(barging),
                payment_terms="30 days net", created_at=now, created_by=buyer, updated_at=now,
                received_at=now + timedelta(hours=min(0, hours - 24)),  # before valid_until
            )  # fmt: skip
            s.add(offer)
            s.flush()
            s.add_all(
                OfferLine(
                    id=uuid.uuid4(),
                    organization_id=db.org,
                    offer_id=offer.id,
                    inquiry_id=inq,
                    inquiry_line_id=lid,
                    price_per_mt=Decimal(price),
                )
                for lid, price in zip(line_ids, prices, strict=True)
                if price is not None
            )
            s.flush()
            offers.append(offer)
        if voyage in _WINNERS:
            idx, reason, note = _WINNERS[voyage]
            winner = offers[idx]
            total = evaluate_offer(offer_repo.inputs_for(s, winner)).total
            db.put(
                "UPDATE inquiry SET winner_offer_id = :w, decision_reason = :r, decision_note = :n,"
                " decided_at = :t, decided_by = :b, decided_total = :d WHERE id = :i",
                w=winner.id, r=reason, n=note, t=now, b=buyer, d=total, i=inq,
            )  # fmt: skip


def _seed_nominations(db: _Org, s: Session, now: datetime, users: dict[str, uuid.UUID]) -> None:
    """DEMO-6: nomination 1, then an ETA change, then amended nomination 2 (texts via the domain).

    Frozen exactly as mark-sent does: the first send bumps the inquiry (winner_selected ->
    nominated), the ETA edit bumps it again, and the amendment is sent against that version.
    """
    inq = s.scalars(
        select(Inquiry)
        .where(Inquiry.voyage == "DEMO-6")
        .order_by(Inquiry.created_at, Inquiry.reference)
        .limit(1)
    ).one()
    if s.scalar(select(Nomination.id).where(Nomination.inquiry_id == inq.id)):
        return
    offer_id = inq.winner_offer_id
    assert offer_id is not None  # noqa: S101  (seeded with its decision)
    contact = s.scalar(select(Rfq.contact_id).join(Offer).where(Offer.id == offer_id))
    assert contact is not None  # noqa: S101  (FK)
    for sequence in (1, 2):
        inq.version += 1  # 1: the move to nominated; 2: the ETA edit
        if sequence == 2:  # noqa: PLR2004
            assert inq.eta is not None  # noqa: S101  (seeded)
            inq.eta += timedelta(hours=24)
            inq.updated_at = now
        nom = Nomination(
            id=uuid.uuid4(), organization_id=db.org, inquiry_id=inq.id, offer_id=offer_id,
            contact_id=contact, status="sent", sequence=sequence, version=2, created_at=now,
            created_by=users["bunker_buyer"], updated_at=now, sent_at=now,
            inquiry_version_at_send=inq.version,
        )  # fmt: skip
        s.flush()
        ctx = nomination_repo.build_nomination_context(s, nom)
        assert ctx.total == inq.decided_total  # noqa: S101  (R6)
        nom.sent_subject, nom.sent_body = render_nomination(ctx)
        nom.sent_to_email = ctx.recipient_email
        s.add(nom)
        s.flush()


def seed(engine: Engine, mode: str | None, now: datetime | None = None) -> None:
    """Seed ``dev`` (Acme, Borealis) or ``pilot`` (Pilot Demo Shipping); unset or empty: nothing."""
    if not mode:
        return
    if mode not in ("dev", "pilot"):
        msg = f"unknown seed mode {mode!r}: expected dev or pilot"
        raise ValueError(msg)
    orgs = PILOT_ORGS if mode == "pilot" else DEV_ORGS
    seed_orgs(engine, orgs)
    seed_demo_master(engine, tuple(orgs))
    seed_demo_inquiries(engine, now, mode)


def main() -> None:
    """Seed the mode in ND_SEED using the owner URL from the environment."""
    seed(create_engine(os.environ["ND_MIGRATION_DATABASE_URL"]), os.environ.get("ND_SEED"))


if __name__ == "__main__":  # pragma: no cover
    main()
