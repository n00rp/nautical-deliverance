"""PostGIS is installed and usable by the runtime role (D-033)."""

from sqlalchemy import Engine, text


def test_postgis_available(app_engine: Engine) -> None:
    """The compose init script creates the extension; nd_app can call it."""
    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT postgis_version()")).scalar_one()
