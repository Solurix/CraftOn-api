"""``Settings.effective_database_url`` — the per-PR preview db-name swap.

Preview environments mount the shared ``crafton-db-url`` secret and set a
non-secret ``CRAFTON_DB_NAME`` so the app targets an isolated ``crafton_pr<N>``
database. Only the db-name segment may change; credentials, the Cloud SQL socket
or host:port, and any query string must be preserved. When ``db_name`` is unset
(dev/CI/prod) the URL is returned unchanged so those paths are untouched.
"""

from __future__ import annotations

from app.core.config import Settings

SOCKET_URL = (
    "postgresql+psycopg://crafton_app:pw@/crafton"
    "?host=/cloudsql/crafton-dev-500709:asia-northeast1:crafton-dev"
)
HOSTPORT_URL = "postgresql+psycopg://crafton:crafton@localhost:5432/crafton"


def test_unset_db_name_returns_url_unchanged() -> None:
    s = Settings(database_url=HOSTPORT_URL, db_name=None)
    assert s.effective_database_url == HOSTPORT_URL


def test_socket_form_swaps_only_db_name() -> None:
    s = Settings(database_url=SOCKET_URL, db_name="crafton_pr42")
    assert s.effective_database_url == (
        "postgresql+psycopg://crafton_app:pw@/crafton_pr42"
        "?host=/cloudsql/crafton-dev-500709:asia-northeast1:crafton-dev"
    )


def test_hostport_form_swaps_only_db_name() -> None:
    s = Settings(database_url=HOSTPORT_URL, db_name="crafton_pr7")
    assert (
        s.effective_database_url
        == "postgresql+psycopg://crafton:crafton@localhost:5432/crafton_pr7"
    )


def test_hostport_form_preserves_query_string() -> None:
    url = "postgresql+psycopg://u:p@db.example:5432/crafton?sslmode=require"
    s = Settings(database_url=url, db_name="crafton_pr9")
    assert (
        s.effective_database_url
        == "postgresql+psycopg://u:p@db.example:5432/crafton_pr9?sslmode=require"
    )
