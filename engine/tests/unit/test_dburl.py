"""Passwords with URL-special characters must survive the entrypoint (B6-R03, C2)."""

import pytest
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy.engine import make_url

from nautical_deliverance.persistence.dburl import quote_password

NASTY = "ab/cd@ef:gh+ij%kl?mn#op=="


@pytest.mark.req("B6-R03")
def test_special_characters_in_the_password_reach_libpq_and_sqlalchemy_intact() -> None:
    url = quote_password(f"postgresql+psycopg://nd_owner:{NASTY}@db:5432/nd")
    assert NASTY not in url
    parsed = make_url(url)
    assert (parsed.username, parsed.password, parsed.host, parsed.port, parsed.database) == (
        "nd_owner",
        NASTY,
        "db",
        5432,
        "nd",
    )
    libpq = conninfo_to_dict(url.replace("+psycopg", ""))
    assert libpq["password"] == NASTY
    assert (libpq["user"], libpq["host"], libpq["port"], libpq["dbname"]) == ("nd_owner", "db", "5432", "nd")


@pytest.mark.req("B6-R03")
def test_plain_and_already_encoded_passwords_are_left_alone() -> None:
    plain = "postgresql+psycopg://nd_app:3f9c0a@db:5432/nd"
    assert quote_password(plain) == plain
    assert quote_password(quote_password(f"postgresql://u:{NASTY}@h/d")) == quote_password(f"postgresql://u:{NASTY}@h/d")
    assert quote_password("postgresql://u@h/d") == "postgresql://u@h/d"
    assert quote_password("postgresql://h/d") == "postgresql://h/d"
