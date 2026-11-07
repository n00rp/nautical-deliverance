"""Percent-encode the password in a database URL (used by docker-entrypoint.sh).

Compose builds ``postgresql+psycopg://user:<password>@db:5432/nd`` from the raw password. A ``/``,
``@`` or ``:`` in it ends the userinfo early for libpq and SQLAlchemy. The host and database parts
never contain ``@``, so the last ``@`` separates the userinfo. Already-encoded passwords stay as they are.
"""

import os
import sys
from urllib.parse import quote, unquote


def quote_password(url: str) -> str:
    """Return ``url`` with the password percent-encoded; URLs without a password are unchanged."""
    scheme, sep, rest = url.partition("://")
    userinfo, at, hostpart = rest.rpartition("@")
    user, colon, password = userinfo.partition(":")
    if not (sep and at and colon):
        return url
    return f"{scheme}://{user}:{quote(unquote(password), safe='')}@{hostpart}"


if __name__ == "__main__":
    print(quote_password(os.environ[sys.argv[1]]))  # noqa: T201 - the entrypoint captures stdout
