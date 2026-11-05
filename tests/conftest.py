"""Shared test setup.

Tests run against a separate PostgreSQL database that is dropped and rebuilt
from the Alembic migrations on every run. PostgreSQL is used rather than SQLite
because order placement relies on row locks and timezone-aware timestamps.

The database comes from TEST_DATABASE_URL. Without it, the tests use
"<name>_test" on the same server as DATABASE_URL in .env, if that server is
local. Any database whose name does not end in "_test" is refused.

The settings below must be in place before anything from `app` is imported,
because app.core.config and app.db.session read them at import time.
"""

import os
import re
from collections.abc import Callable, Iterator
from itertools import count
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parent.parent
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _resolve_test_database_url() -> URL:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        url = make_url(explicit)
    else:
        base = dotenv_values(ROOT / ".env").get("DATABASE_URL")
        if not base:
            pytest.exit("Set TEST_DATABASE_URL to run the tests.", returncode=2)
        base_url = make_url(base)
        if base_url.host not in LOCAL_HOSTS:
            pytest.exit(
                "DATABASE_URL is not a local server. Set TEST_DATABASE_URL.",
                returncode=2,
            )
        url = base_url.set(database=f"{base_url.database}_test")

    if not re.fullmatch(r"\w+_test", url.database or ""):
        pytest.exit(
            f"Refusing to use database {url.database!r}: its name must end in _test.",
            returncode=2,
        )
    return url


TEST_DATABASE_URL = _resolve_test_database_url()

os.environ["DATABASE_URL"] = TEST_DATABASE_URL.render_as_string(hide_password=False)
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-that-is-long-enough-for-hs256"
# Without these, app.services.email cannot reach the real email provider, even
# if a test forgets the `outbox` stub.
os.environ["RESEND_API_KEY"] = ""
os.environ["EMAIL_FROM"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.api.routes.auth as auth_routes  # noqa: E402
import app.api.routes.order as order_routes  # noqa: E402
import app.services.email as email_service  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models import Customer, Product  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

PASSWORD = "Correct-Horse-9"
# Hashing is deliberately slow, so reuse one hash for customers made directly.
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def test_database() -> Iterator[None]:
    """Rebuild the test database from the migrations once per run."""
    if engine.url.database != TEST_DATABASE_URL.database:
        pytest.exit("The app is not connected to the test database.", returncode=2)

    name = TEST_DATABASE_URL.database
    server = create_engine(
        TEST_DATABASE_URL.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with server.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    server.dispose()

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(config, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables(test_database: None) -> None:
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Collect emails instead of sending them."""
    sent: list[dict[str, str]] = []

    async def fake_send_email(to_email: str, subject: str, html: str) -> None:
        sent.append({"to": to_email, "subject": subject, "html": html})

    monkeypatch.setattr(email_service, "send_email", fake_send_email)
    monkeypatch.setattr(auth_routes, "send_email", fake_send_email)
    monkeypatch.setattr(order_routes, "send_email", fake_send_email)
    return sent


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


@pytest.fixture
def db() -> Iterator:
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def make_customer(db) -> Callable[..., Customer]:
    numbers = count(1)

    def factory(**overrides) -> Customer:
        number = next(numbers)
        values = {
            "name": f"Customer {number}",
            "email": f"customer{number}@example.com",
            "hashed_password": PASSWORD_HASH,
            "email_verified": True,
            "customer_type": "retail",
            "role": "customer",
            "is_active": True,
        }
        customer = Customer(**(values | overrides))
        db.add(customer)
        db.commit()
        return customer

    return factory


@pytest.fixture
def make_product(db) -> Callable[..., Product]:
    numbers = count(1)

    def factory(**overrides) -> Product:
        number = next(numbers)
        values = {
            "name": f"Product {number}",
            "category": "Rice",
            "unit": "kg",
            "retail_price": 100,
            "wholesale_price": 80,
            "min_wholesale_quantity": 25,
            "stock_quantity": 50,
            "is_active": True,
        }
        product = Product(**(values | overrides))
        db.add(product)
        db.commit()
        return product

    return factory


@pytest.fixture
def auth() -> Callable[[Customer], dict[str, str]]:
    def headers(customer: Customer) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(customer.id)}"}

    return headers


@pytest.fixture
def make_address(client, auth) -> Callable[..., int]:
    def factory(customer: Customer, **overrides) -> int:
        values = {
            "recipient_name": "Test Person",
            "phone": "9876543210",
            "address_line1": "12 Farm Road",
            "city": "Guntur",
            "state": "Andhra Pradesh",
            "postal_code": "522001",
        }
        response = client.post(
            "/api/addresses/", json=values | overrides, headers=auth(customer)
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    return factory


@pytest.fixture
def add_to_cart(client, auth) -> Callable[..., dict]:
    def add(customer: Customer, product: Product, quantity: int = 1) -> dict:
        response = client.post(
            "/api/cart/items",
            json={"product_id": product.id, "quantity": quantity},
            headers=auth(customer),
        )
        assert response.status_code == 200, response.text
        return response.json()

    return add
