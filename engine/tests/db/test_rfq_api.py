"""RFQ suggestions, drafts, log, preview, edit (B3-R01..R06, R10, R11)."""

import dataclasses
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine, select, update

from nautical_deliverance.domain.identity import Role
from nautical_deliverance.domain.rfq import RfqContext, render_rfq
from nautical_deliverance.persistence import rfq_repo
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.master_repo import counterparties_covering
from nautical_deliverance.persistence.models import (
    AppUser,
    AuditEntry,
    Contact,
    Counterparty,
    Coverage,
    Inquiry,
    LegalEntity,
    Port,
    Product,
    Rfq,
)
from tests.db.test_inquiry_api import (
    CONFLICT,
    CREATED,
    FORBIDDEN,
    NOT_FOUND,
    OK,
    Client,
    errors,
    line,
    make_world,
)
from tests.unit.test_rfq_domain import ALLOWED
from tests.unit.test_rfq_domain import FORBIDDEN as NEVER

if TYPE_CHECKING:
    from types import SimpleNamespace

    from nautical_deliverance.settings import Settings

type Json = Any

DEADLINE = "2026-11-10T08:00:00Z"
V2 = 2
PAST = "2026-11-01T08:00:00Z"


def _add(s: Any, model: type, **kw: Any) -> uuid.UUID:  # noqa: ANN401
    kw.setdefault("id", uuid.uuid4())
    s.add(model(**kw))
    ident: uuid.UUID = kw["id"]
    return ident


def rfq_world(engine: Engine, name: str = "") -> SimpleNamespace:
    """Build a world plus suppliers (Alpha: HSFO+MGO, Beta: HSFO, Gamma: none, Delta: inactive)."""
    w = make_world(engine, name)
    org = w.org
    w.cp, w.ct = {}, {}
    with org_session(org, engine) as s:
        for cp, kind, active in (
            ("Alpha", "physical_supplier", True),
            ("Beta", "trader", True),
            ("Gamma", "both", True),
            ("Delta", "trader", False),
        ):
            w.cp[cp] = _add(
                s, Counterparty, organization_id=org, name=f"{cp} Marine", type=kind, active=active
            )
        s.flush()
        contacts = (
            ("a1", "Alpha", True, True, ""),
            ("a2", "Alpha", False, True, ""),
            ("a_off", "Alpha", False, False, ""),
            ("a_blank", "Alpha", False, True, "BLANK"),
            ("b1", "Beta", True, True, ""),
            ("c1", "Gamma", True, True, ""),
            ("d1", "Delta", True, True, ""),
        )
        for key, cp, primary, active, flag in contacts:
            w.ct[key] = _add(
                s, Contact, organization_id=org, counterparty_id=w.cp[cp], name=f"Name {key}",
                email="" if flag else f"{key}@{cp.lower()}.example", is_primary=primary,
                active=active,
            )  # fmt: skip
        s.flush()
        for cp, products in (
            ("Alpha", (w.hsfo, w.mgo)),
            ("Beta", (w.hsfo,)),
            ("Delta", (w.hsfo, w.mgo)),
        ):
            for p in products:
                _add(
                    s, Coverage, organization_id=org, counterparty_id=w.cp[cp],
                    port_id=w.port, product_id=p,
                )  # fmt: skip
    return w


def deactivate(w: SimpleNamespace, engine: Engine, model: type, ident: uuid.UUID) -> None:
    """Deactivate one master row directly."""
    with org_session(w.org, engine) as s:
        s.execute(update(model).where(model.id == ident).values(active=False))  # type: ignore[attr-defined]


class Rc(Client):
    """Client with RFQ helpers."""

    def inquiry(self, **over: Any) -> Json:  # noqa: ANN401
        """Create an inquiry with the HSFO and MGO lines (buyer = caller if a buyer)."""
        return self.create(lines=[line(self.w), line(self.w, product_id=str(self.w.mgo))], **over)

    def recipients(self, *pairs: tuple[str, str]) -> list[dict[str, str]]:
        """Recipient bodies from (counterparty, contact) keys."""
        return [
            {"counterparty_id": str(self.w.cp[c]), "contact_id": str(self.w.ct[k])}
            for c, k in pairs
        ]

    def post(self, inq_id: str, pairs: list[tuple[str, str]], deadline: str = DEADLINE) -> Any:  # noqa: ANN401
        """POST /inquiries/{id}/rfqs."""
        return self.http.post(
            f"/api/v1/inquiries/{inq_id}/rfqs",
            json={"deadline": deadline, "recipients": self.recipients(*pairs)},
        )

    def make(self, inq_id: str, *pairs: tuple[str, str]) -> list[Json]:
        """Create drafts and return the created items."""
        r = self.post(inq_id, list(pairs))
        assert r.status_code == CREATED, r.text
        items: list[Json] = r.json()
        return items

    def api(self, path: str) -> Json:
        """GET under /api/v1, expecting 200."""
        r = self.http.get(f"/api/v1{path}")
        assert r.status_code == OK, r.text
        return r.json()

    def fresh(self, inq: Json) -> Json:
        """Return the inquiry as it is now (its version moves when RFQs set the deadline)."""
        return super().get(inq["id"])

    def audit(self, entity_type: str, ids: list[str] | None = None) -> list[AuditEntry]:
        """Audit entries of a type (optionally of given entity ids), oldest first."""
        with org_session(self.w.org, self.engine) as s:
            stmt = select(AuditEntry).where(AuditEntry.entity_type == entity_type)
            if ids is not None:
                stmt = stmt.where(AuditEntry.entity_id.in_([uuid.UUID(i) for i in ids]))
            rows = list(s.scalars(stmt.order_by(AuditEntry.at)))
            s.expunge_all()
            return rows


def make_client(settings: Settings, engine: Engine, w: SimpleNamespace, role: Role) -> Rc:
    """Client of one role."""
    return Rc(settings, engine, w, role)


@pytest.fixture
def world(app_engine: Engine) -> SimpleNamespace:
    """World with suppliers."""
    return rfq_world(app_engine)


@pytest.fixture
def admin(settings: Settings, app_engine: Engine, world: SimpleNamespace) -> Rc:
    """Admin client."""
    return make_client(settings, app_engine, world, Role.ADMIN)


@pytest.fixture
def inq(admin: Rc) -> Json:
    """Create a draft inquiry with a buyer."""
    return admin.inquiry()


# --- B3-R03: roles -------------------------------------------------------------------------------

ROUTES: list[tuple[str, str, bool]] = [
    ("GET", "/inquiries/{inq}/suggestions", False),
    ("GET", "/inquiries/{inq}/rfqs", False),
    ("GET", "/rfqs/{rfq}/preview", False),
    ("GET", "/rfqs/{rfq}/history", False),
    ("POST", "/inquiries/{inq}/rfqs", True),
    ("PATCH", "/rfqs/{rfq}", True),
    ("POST", "/rfqs/{rfq}/mark-sent", True),
    ("POST", "/rfqs/{rfq}/withdraw", True),
    ("POST", "/rfqs/{rfq}/decline", True),
]


@pytest.mark.req("B3-R03")
@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize(("method", "path", "writes"), ROUTES)
def test_role_matrix(  # noqa: PLR0913
    settings: Settings, app_engine: Engine, world: SimpleNamespace,
    *, method: str, path: str, writes: bool, role: Role,
) -> None:  # fmt: skip
    """Operator gets 403 everywhere; Viewer reads but cannot write; Admin and Buyer do both."""
    admin = make_client(settings, app_engine, world, Role.ADMIN)
    i = admin.inquiry()
    rfq = admin.make(i["id"], ("Alpha", "a1"))[0]
    version = 1
    if path.endswith("/decline"):  # only a sent RFQ can be declined
        sent = admin.http.post(f"/api/v1/rfqs/{rfq['id']}/mark-sent", json={"version": 1})
        assert sent.status_code == OK, sent.text
        version = 2
    url = "/api/v1" + path.format(inq=i["id"], rfq=rfq["id"])
    creates = path == "/inquiries/{inq}/rfqs" and method == "POST"
    body: Json = {"version": version} if writes else None
    if creates:
        body = {"deadline": DEADLINE, "recipients": admin.recipients(("Beta", "b1"))}
    r = make_client(settings, app_engine, world, role).http.request(method, url, json=body)
    allowed = role is not Role.OPERATOR and not (writes and role is Role.VIEWER)
    expected = (CREATED if creates else OK) if allowed else FORBIDDEN
    assert r.status_code == expected, r.text


# --- B3-R04: suggestions -------------------------------------------------------------------------


def groups(s: Json) -> tuple[list[str], list[str], list[str]]:
    """Group member names."""
    return tuple([e["name"] for e in s[k]] for k in ("covers_all", "covers_some", "not_listed"))  # type: ignore[return-value]


@pytest.mark.req("B3-R04")
def test_suggestion_groups(
    admin: Rc, inq: Json, world: SimpleNamespace, app_engine: Engine
) -> None:
    """A covers all, B some, C none; Delta is inactive; contacts are active with an e-mail."""
    s = admin.api(f"/inquiries/{inq['id']}/suggestions")
    assert groups(s) == (["Alpha Marine"], ["Beta Marine"], ["Gamma Marine"])
    alpha = s["covers_all"][0]
    assert alpha["counterparty_id"] == str(world.cp["Alpha"])
    assert alpha["type"] == "physical_supplier"
    assert [c["id"] for c in alpha["contacts"]] == [str(world.ct["a1"]), str(world.ct["a2"])]
    assert alpha["contacts"][0] == {
        "id": str(world.ct["a1"]), "name": "Name a1", "email": "a1@alpha.example",
        "is_primary": True,
    }  # fmt: skip
    assert alpha["primary_contact_id"] == str(world.ct["a1"])
    assert sorted(alpha["covered_product_ids"]) == sorted([str(world.hsfo), str(world.mgo)])
    assert alpha["active_rfq_id"] is None
    assert s["covers_some"][0]["covered_product_ids"] == [str(world.hsfo)]
    assert s["not_listed"][0]["covered_product_ids"] == []
    with org_session(world.org, app_engine) as db:
        modes: tuple[tuple[str, Literal["all", "some"]], ...] = (
            ("covers_all", "all"),
            ("covers_some", "some"),
        )
        for key, mode in modes:
            ids = [
                c.id
                for c in counterparties_covering(db, world.port, [world.hsfo, world.mgo], mode=mode)
            ]
            assert [uuid.UUID(e["counterparty_id"]) for e in s[key]] == ids


@pytest.mark.req("B3-R04")
@pytest.mark.parametrize(
    ("what", "expected"),
    [
        ("contact", (["Alpha Marine"], ["Beta Marine"], ["Gamma Marine"])),
        ("counterparty", ([], ["Beta Marine"], ["Gamma Marine"])),
        ("product", (["Alpha Marine", "Beta Marine"], [], ["Gamma Marine"])),
        ("port", ([], [], ["Alpha Marine", "Beta Marine", "Gamma Marine"])),
    ],
)
def test_suggestions_exclude_inactive(  # noqa: PLR0913, PLR0917
    admin: Rc, inq: Json, world: SimpleNamespace, app_engine: Engine,
    what: str, expected: tuple[list[str], ...],
) -> None:  # fmt: skip
    """Inactive contacts, counterparties, products and ports are each left out."""
    target = {
        "contact": (Contact, world.ct["a2"]),
        "counterparty": (Counterparty, world.cp["Alpha"]),
        "product": (Product, world.mgo),
        "port": (Port, world.port),
    }[what]
    deactivate(world, app_engine, *target)
    s = admin.api(f"/inquiries/{inq['id']}/suggestions")
    assert groups(s) == expected
    if what == "port":
        assert all(e["covered_product_ids"] == [] for e in s["not_listed"])
    if what == "contact":
        assert [c["id"] for c in s["covers_all"][0]["contacts"]] == [str(world.ct["a1"])]


@pytest.mark.req("B3-R04")
def test_suggestions_show_active_rfq(admin: Rc, inq: Json) -> None:
    """A counterparty with an active RFQ carries its id; contactless ones still appear."""
    rfq = admin.make(inq["id"], ("Alpha", "a1"))[0]
    s = admin.api(f"/inquiries/{inq['id']}/suggestions")
    assert s["covers_all"][0]["active_rfq_id"] == rfq["id"]
    assert s["covers_some"][0]["active_rfq_id"] is None


# --- B3-R05: one draft per recipient -------------------------------------------------------------

SUBSETS = st.sets(
    st.sampled_from([("Alpha", "a1"), ("Alpha", "a2"), ("Beta", "b1"), ("Gamma", "c1")]),
    min_size=1,
).filter(lambda s: len({c for c, _ in s}) == len(s))


@pytest.mark.req("B3-R05")
@settings(
    max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(subset=SUBSETS)
def test_one_draft_per_recipient(
    settings: Settings, app_engine: Engine, subset: set[tuple[str, str]]
) -> None:
    """Any recipient subset gives that many drafts, each addressed to its own contact."""
    w = rfq_world(app_engine)
    c = make_client(settings, app_engine, w, Role.ADMIN)
    i = c.inquiry()
    items = c.make(i["id"], *sorted(subset))
    assert len(items) == len(subset)
    for item in items:
        p = c.api(f"/rfqs/{item['id']}/preview")
        assert p["to"] == item["email"]
        assert p["to"] in {f"{k}@{cp.lower()}.example" for cp, k in subset}
        assert f"Dear {item['contact_name']}," in p["body"]
        assert p["mailto"].startswith(f"mailto:{p['to']}?subject=")
        assert p["mailto"].count("@") == 1 + p["mailto"].count("%40")
        assert not any(k in p["mailto"] for k in ("cc=", "bcc=", "&to=", ","))
    assert len({x["id"] for x in items}) == len(subset)
    assert sorted(x["email"] for x in items) == sorted(
        f"{k}@{cp.lower()}.example" for cp, k in subset
    )


# --- create, log, preview, edit shapes (B3-R05) ---------------------------------------------


@pytest.mark.req("B3-R05")
def test_create_log_and_preview_shape(admin: Rc, inq: Json, world: SimpleNamespace) -> None:
    """Items, the log and the preview have the specified shapes; the draft is live."""
    items = admin.make(inq["id"], ("Beta", "b1"), ("Alpha", "a2"))
    keys = {
        "id", "counterparty_name", "contact_name", "email", "generated_at", "sent_at", "status",
        "response_deadline", "offer_received", "changed_since_sent", "version",
    }  # fmt: skip
    for x in items:
        assert set(x) == keys
        assert (x["status"], x["sent_at"], x["version"]) == ("draft", None, 1)
        assert (x["offer_received"], x["changed_since_sent"]) == (False, False)
        assert x["generated_at"].startswith("2026-11-05T12:00:00")
        assert x["response_deadline"].startswith("2026-11-10T08:00:00")
    assert admin.api(f"/inquiries/{inq['id']}/rfqs") == sorted(
        items, key=lambda x: x["counterparty_name"]
    )
    with org_session(world.org, admin.engine) as s:
        got = s.get(Inquiry, uuid.UUID(inq["id"]))
        assert got is not None
        assert got.rfq_deadline == datetime(2026, 11, 10, 8, tzinfo=UTC)
    rfq = items[0]
    p = admin.api(f"/rfqs/{rfq['id']}/preview")
    assert set(p) == {"to", "subject", "body", "mailto", "body_in_link"}
    assert p["subject"] == f"RFQ {inq['reference']} – Vessel A – Rotterdam"  # noqa: RUF001
    assert p["mailto"].startswith(f"mailto:{rfq['email']}?subject=")
    assert p["body_in_link"] is True
    assert "Agent: to be advised" in p["body"]
    admin.patch(admin.fresh(inq), agent_name="Fresh Agent")
    assert "Agent: Fresh Agent" in admin.api(f"/rfqs/{rfq['id']}/preview")["body"]


@pytest.mark.req("B3-R05")
def test_long_body_drops_from_link(admin: Rc, world: SimpleNamespace) -> None:
    """A body over the mailto limit is left out of the link."""
    i = admin.create(
        lines=[line(world, product_id=str(p), spec_notes="n" * 400) for p in world.many]
    )
    rfq = admin.make(i["id"], ("Alpha", "a1"))[0]
    p = admin.api(f"/rfqs/{rfq['id']}/preview")
    assert p["body_in_link"] is False
    assert "body=" not in p["mailto"]


# --- B3-R06: confidentiality ---------------------------------------------------------------------


@pytest.mark.req("B3-R06")
def test_context_fields_pinned(admin: Rc, inq: Json, world: SimpleNamespace) -> None:
    """build_context returns exactly the allow-listed fields."""
    expected = [*ALLOWED, "recipient_name", "recipient_email", "buyer_name"]
    assert sorted(f.name for f in dataclasses.fields(RfqContext)) == sorted(expected)
    assert not set(NEVER) & set(expected)
    item = admin.make(inq["id"], ("Alpha", "a1"))[0]
    with org_session(world.org, admin.engine) as s:
        ctx = rfq_repo.build_context(s, s.get(Rfq, uuid.UUID(item["id"])))  # type: ignore[arg-type]
        assert {f.name for f in dataclasses.fields(ctx)} == set(expected)
        assert ctx.recipient_email == "a1@alpha.example"


# FORBIDDEN keys with no DB column or table behind them (a marker cannot be planted).
NO_SOURCE = frozenset(
    {"recipient_count", "price_expectation", "offer_price", "decision_rationale", "comparison_note"}
)
# Which counterparty legitimately owns a marker (its own preview may show it).
OWNER = {
    "recipient_counterparty_name": "Alpha", "other_cp_name_1": "Beta", "other_cp_name_2": "Gamma",
    "other_contact_email_1": "Beta", "other_contact_email_2": "Gamma",
    "other_contact_name": "Gamma",
}  # fmt: skip


@pytest.mark.req("B3-R06")
def test_preview_has_no_forbidden_data(admin: Rc, world: SimpleNamespace) -> None:
    """A marker in every forbidden source with a DB counterpart never reaches another preview."""
    mk = {k: f"MK-{k.upper()}-ZZ" for k in NEVER if k not in NO_SOURCE}
    mk["other_contact_email_1"] = "mk-other1@mk-one.example"
    mk["other_contact_email_2"] = "mk-other2@mk-two.example"
    assert set(mk) | NO_SOURCE == set(NEVER)
    viewer = world.users[Role.VIEWER].user_id
    i = admin.inquiry(
        internal_comments=mk["internal_comments"], voyage=mk["voyage"],
        agent_email="x@mk-agent.example", requester_id=str(viewer),
    )  # fmt: skip
    admin.make(i["id"], ("Alpha", "a1"), ("Beta", "b1"), ("Gamma", "c1"))
    names = {"Alpha": "recipient_counterparty_name", "Beta": "other_cp_name_1",
             "Gamma": "other_cp_name_2"}  # fmt: skip
    with org_session(world.org, admin.engine) as s:
        for cp, key in names.items():
            s.execute(
                update(Counterparty).where(Counterparty.id == world.cp[cp]).values(name=mk[key])
            )
        for ct, key in (("b1", "other_contact_email_1"), ("c1", "other_contact_email_2")):
            s.execute(update(Contact).where(Contact.id == world.ct[ct]).values(email=mk[key]))
        s.execute(
            update(Contact)
            .where(Contact.id == world.ct["c1"])
            .values(name=mk["other_contact_name"])
        )
        s.execute(update(AppUser).where(AppUser.id == viewer).values(name=mk["requester_name"]))
        op = world.users[Role.OPERATOR].user_id
        s.execute(update(AppUser).where(AppUser.id == op).values(name=mk["operator_name"]))
        s.execute(update(LegalEntity).values(name=mk["legal_entity_name"]))
        s.execute(
            update(Inquiry).where(Inquiry.id == uuid.UUID(i["id"]))
            .values(status="cancelled", cancel_reason=mk["cancel_reason"])
        )  # fmt: skip
    mk["agent_email"] = "mk-agent.example"
    for item in admin.api(f"/inquiries/{i['id']}/rfqs"):
        mine = next(c for c, k in names.items() if item["counterparty_name"] == mk[k])
        p = admin.api(f"/rfqs/{item['id']}/preview")
        text_ = "\n".join(str(v) for v in p.values())
        for key, value in mk.items():
            if OWNER.get(key) != mine:
                assert value not in text_, (mine, key)
        assert item["email"] in text_


# --- B3-R01: validation --------------------------------------------------------------------------

BAD: list[tuple[str, str, list[tuple[str, str]], str]] = [
    ("recipients[0].counterparty_id", "Inactive counterparty", [("Delta", "d1")], DEADLINE),
    ("recipients[1].contact_id", "Inactive contact",
     [("Beta", "b1"), ("Alpha", "a_off")], DEADLINE),
    ("recipients[0].contact_id", "Contact has no e-mail address", [("Alpha", "a_blank")], DEADLINE),
    ("recipients[0].contact_id", "Contact belongs to another counterparty",
     [("Alpha", "b1")], DEADLINE),
    ("recipients[1].counterparty_id", "Duplicate counterparty",
     [("Alpha", "a1"), ("Alpha", "a2")], DEADLINE),
    ("deadline", "Must be in the future", [("Alpha", "a1")], PAST),
    ("deadline", "Must be in the future", [("Alpha", "a1")], "2026-11-05T12:00:00Z"),
]  # fmt: skip


@pytest.mark.req("B3-R01")
@pytest.mark.parametrize(("field", "message", "pairs", "deadline"), BAD)
def test_create_validation(  # noqa: PLR0913, PLR0917
    admin: Rc, inq: Json, field: str, message: str, pairs: list[tuple[str, str]], deadline: str
) -> None:
    """Each rule rejects with its exact field path and creates nothing (atomic)."""
    r = admin.post(inq["id"], pairs, deadline)
    assert errors(r)[field] == message
    assert admin.api(f"/inquiries/{inq['id']}/rfqs") == []
    assert admin.audit("rfq") == []


@pytest.mark.req("B3-R01")
def test_create_validation_misc(admin: Rc, inq: Json, world: SimpleNamespace) -> None:
    """No buyer, unknown ids, empty list and naive deadline."""
    nobuyer = admin.inquiry(buyer_id=None)
    r = admin.post(nobuyer["id"], [("Alpha", "a1")])
    assert errors(r) == {"buyer_id": "Assign a buyer before creating RFQs"}
    unknown = str(uuid.uuid4())
    r = admin.http.post(
        f"/api/v1/inquiries/{inq['id']}/rfqs",
        json={"deadline": DEADLINE, "recipients": [
            {"counterparty_id": unknown, "contact_id": str(world.ct["a1"])},
            {"counterparty_id": str(world.cp["Alpha"]), "contact_id": unknown},
        ]},
    )  # fmt: skip
    assert errors(r) == {
        "recipients[0].counterparty_id": "Unknown counterparty",
        "recipients[1].contact_id": "Unknown contact",
    }
    assert "recipients" in errors(admin.http.post(
        f"/api/v1/inquiries/{inq['id']}/rfqs", json={"deadline": DEADLINE, "recipients": []}
    ))  # fmt: skip
    assert "deadline" in errors(admin.post(inq["id"], [("Alpha", "a1")], "2026-12-01T00:00:00"))


# --- B3-R02: organization isolation --------------------------------------------------------------


@pytest.mark.req("B3-R02")
def test_other_org(settings: Settings, app_engine: Engine, admin: Rc, inq: Json) -> None:
    """Another org's inquiry and RFQ ids are 404; its suppliers are unknown (422)."""
    rfq = admin.make(inq["id"], ("Alpha", "a1"))[0]
    w2 = rfq_world(app_engine, "o2")
    other = make_client(settings, app_engine, w2, Role.ADMIN)
    mine = other.inquiry()
    for method, path, body in (
        ("GET", f"/inquiries/{inq['id']}/suggestions", None),
        ("GET", f"/inquiries/{inq['id']}/rfqs", None),
        ("POST", f"/inquiries/{inq['id']}/rfqs",
         {"deadline": DEADLINE, "recipients": other.recipients(("Alpha", "a1"))}),
        ("GET", f"/rfqs/{rfq['id']}/preview", None),
        ("PATCH", f"/rfqs/{rfq['id']}", {"version": 1}),
    ):  # fmt: skip
        assert other.http.request(method, "/api/v1" + path, json=body).status_code == NOT_FOUND
    foreign = [
        {"counterparty_id": str(admin.w.cp["Beta"]), "contact_id": str(w2.ct["b1"])},
        {"counterparty_id": str(w2.cp["Beta"]), "contact_id": str(admin.w.ct["b1"])},
    ]
    r = other.http.post(
        f"/api/v1/inquiries/{mine['id']}/rfqs", json={"deadline": DEADLINE, "recipients": foreign}
    )
    assert errors(r) == {
        "recipients[0].counterparty_id": "Unknown counterparty",
        "recipients[1].contact_id": "Unknown contact",
    }
    own = other.make(mine["id"], ("Alpha", "a1"))[0]
    r = other.http.patch(
        f"/api/v1/rfqs/{own['id']}", json={"version": 1, "contact_id": str(admin.w.ct["a2"])}
    )
    assert errors(r) == {"contact_id": "Unknown contact"}


# --- B3-R10: inquiry status, duplicates, inactive contacts ---------------------------------------


@pytest.mark.req("B3-R10")
@pytest.mark.parametrize(
    ("state", "code"),
    [
        ("draft", CREATED), ("rfq_sent", CREATED), ("offers_received", CREATED),
        ("winner_selected", CONFLICT), ("nominated", CONFLICT), ("cancelled", CONFLICT),
    ],
)  # fmt: skip
def test_create_by_inquiry_status(admin: Rc, inq: Json, state: str, code: int) -> None:
    """Only open inquiries before the winner accept new drafts."""
    admin.set_status(inq["id"], state)
    assert admin.post(inq["id"], [("Alpha", "a1")]).status_code == code


@pytest.mark.req("B3-R10")
def test_one_active_rfq_per_counterparty(admin: Rc, inq: Json) -> None:
    """A second RFQ to the same counterparty is rejected, also with another contact."""
    admin.make(inq["id"], ("Alpha", "a1"))
    r = admin.post(inq["id"], [("Beta", "b1"), ("Alpha", "a2")])
    assert errors(r) == {"recipients[1].counterparty_id": "Already has an RFQ"}
    assert len(admin.api(f"/inquiries/{inq['id']}/rfqs")) == 1


@pytest.mark.req("B3-R10")
def test_deactivated_contact_after_create(admin: Rc, inq: Json, world: SimpleNamespace) -> None:
    """A contact deactivated later stays in the log but is neither offered nor accepted."""
    rfq = admin.make(inq["id"], ("Alpha", "a1"))[0]
    deactivate(world, admin.engine, Contact, world.ct["a1"])
    log = admin.api(f"/inquiries/{inq['id']}/rfqs")
    assert [(x["id"], x["email"]) for x in log] == [(rfq["id"], "a1@alpha.example")]
    other = admin.inquiry()
    s = admin.api(f"/inquiries/{other['id']}/suggestions")
    assert [c["id"] for c in s["covers_all"][0]["contacts"]] == [str(world.ct["a2"])]
    assert s["covers_all"][0]["primary_contact_id"] is None
    r = admin.post(other["id"], [("Alpha", "a1")])
    assert errors(r) == {"recipients[0].contact_id": "Inactive contact"}


# --- B3-R11: audit -------------------------------------------------------------------------------


@pytest.mark.req("B3-R11")
def test_audit(admin: Rc, inq: Json, world: SimpleNamespace) -> None:
    """Create: one entry per RFQ and one for the inquiry deadline. Patch: one; no-op: none."""
    before = len(admin.audit("inquiry"))
    items = admin.make(inq["id"], ("Alpha", "a1"), ("Beta", "b1"))
    entries = admin.audit("rfq")
    assert sorted(str(e.entity_id) for e in entries) == sorted(x["id"] for x in items)
    assert {e.action for e in entries} == {"create"}
    mine = next(e for e in entries if str(e.entity_id) == items[0]["id"])
    assert mine.changes["status"] == {"before": None, "after": "draft"}
    assert mine.changes["contact_id"]["after"] == str(world.ct["a1"])
    inquiry_entries = admin.audit("inquiry")[before:]
    assert [(e.action, set(e.changes)) for e in inquiry_entries] == [("update", {"rfq_deadline"})]
    # Same deadline again: nothing changes on the inquiry.
    admin.make(inq["id"], ("Gamma", "c1"))
    assert len(admin.audit("inquiry")) == before + 1

    a = items[0]
    ok = admin.http.patch(
        f"/api/v1/rfqs/{a['id']}", json={"version": 1, "contact_id": str(world.ct["a2"])}
    )
    assert ok.status_code == OK
    assert ok.json()["email"] == "a2@alpha.example"
    assert (ok.json()["contact_name"], ok.json()["version"]) == ("Name a2", 2)
    patched = admin.audit("rfq", [a["id"]])
    assert [e.action for e in patched] == ["create", "update"]
    assert patched[-1].changes == {
        "contact_id": {"before": str(world.ct["a1"]), "after": str(world.ct["a2"])}
    }
    noop = admin.http.patch(
        f"/api/v1/rfqs/{a['id']}",
        json={"version": 2, "contact_id": str(world.ct["a2"]), "response_deadline": DEADLINE},
    )
    assert noop.status_code == OK
    assert noop.json()["version"] == V2
    assert len(admin.audit("rfq", [a["id"]])) == V2


# --- edit (PATCH) --------------------------------------------------------------------------------


@pytest.mark.req("B3-R01")
def test_patch_rules(admin: Rc, inq: Json, world: SimpleNamespace) -> None:
    """Deadline edit, stale version, validation and draft-only."""
    a = admin.make(inq["id"], ("Alpha", "a1"))[0]
    url = f"/api/v1/rfqs/{a['id']}"
    new = "2026-11-12T10:00:00Z"
    r = admin.http.patch(url, json={"version": 1, "response_deadline": new})
    assert r.status_code == OK
    assert r.json()["response_deadline"].startswith("2026-11-12T10:00:00")
    stale = admin.http.patch(url, json={"version": 1, "response_deadline": DEADLINE})
    assert (stale.status_code, stale.json()) == (
        CONFLICT, {"detail": "Record was changed by someone else"}
    )  # fmt: skip
    for field, value, message in (
        ("response_deadline", PAST, "Must be in the future"),
        ("contact_id", str(world.ct["b1"]), "Contact belongs to another counterparty"),
        ("contact_id", str(world.ct["a_off"]), "Inactive contact"),
        ("contact_id", str(world.ct["a_blank"]), "Contact has no e-mail address"),
    ):
        r = admin.http.patch(url, json={"version": 2, field: value})
        assert errors(r) == {field: message}
    with org_session(world.org, admin.engine) as s:
        s.execute(update(Rfq).where(Rfq.id == uuid.UUID(a["id"])).values(status="withdrawn"))
    r = admin.http.patch(url, json={"version": 2, "response_deadline": DEADLINE})
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, "RFQ is not a draft")


# --- changed_since_sent (used by Task 4) ---------------------------------------------------------


@pytest.mark.req("B3-R08")
def test_changed_since_sent(admin: Rc, inq: Json, world: SimpleNamespace) -> None:
    """A frozen text that no longer matches the live render is flagged (function and log)."""
    rfq = admin.make(inq["id"], ("Alpha", "a1"))[0]
    rid = uuid.UUID(rfq["id"])
    with org_session(world.org, admin.engine) as s:
        row = s.get(Rfq, rid)
        assert row is not None
        assert rfq_repo.changed_since_sent(s, row) is False  # a draft has nothing frozen
        subject, body = render_rfq(rfq_repo.build_context(s, row))
        row.status, row.sent_at = "sent", datetime(2026, 11, 5, 13, tzinfo=UTC)
        row.sent_to_email, row.sent_subject, row.sent_body = "a1@alpha.example", subject, body
        row.inquiry_version_at_send = 1
        s.flush()
        assert rfq_repo.changed_since_sent(s, row) is False
    assert admin.api(f"/inquiries/{inq['id']}/rfqs")[0]["changed_since_sent"] is False
    admin.patch(admin.fresh(inq), agent_name="Changed Agent")
    with org_session(world.org, admin.engine) as s:
        row = s.get(Rfq, rid)
        assert row is not None
        assert rfq_repo.changed_since_sent(s, row) is True
    item = admin.api(f"/inquiries/{inq['id']}/rfqs")[0]
    assert item["changed_since_sent"] is True
    assert item["email"] == "a1@alpha.example"
    assert item["status"] == "sent"
    # The preview of a sent RFQ is the frozen text, not the live one.
    assert "Changed Agent" not in admin.api(f"/rfqs/{rid}/preview")["body"]


@pytest.mark.req("B3-R13")
def test_work_list_counts_active_and_sent_rfqs(admin: Rc, inq: Json) -> None:
    """rfq_total counts every RFQ but withdrawn ones; rfq_sent counts sent and declined."""
    assert admin.api("/inquiries")[0]["rfq_total"] == 0
    a, b, c = admin.make(inq["id"], ("Alpha", "a1"), ("Beta", "b1"), ("Gamma", "c1"))

    def act(rfq: Json, action: str) -> Json:
        r = admin.http.post(f"/api/v1/rfqs/{rfq['id']}/{action}", json={"version": rfq["version"]})
        assert r.status_code == OK, r.text
        item: Json = r.json()
        return item

    act(a, "mark-sent")
    act(act(b, "mark-sent"), "decline")
    act(c, "withdraw")
    row = admin.api("/inquiries")[0]
    assert (row["rfq_total"], row["rfq_sent"]) == (2, 2)
    assert admin.fresh(inq)["rfq_deadline"] == DEADLINE
