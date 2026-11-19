import pytest

from app import cli
from app.models import Product
from app.seed_data import SEED_PRODUCTS


class TestPromoteAdmin:
    def test_promotes_existing_verified_account(self, db, make_customer):
        customer = make_customer(email="owner@example.com")

        cli.promote_admin(db, "  OWNER@example.com ")

        db.expire_all()
        assert customer.role == "admin"

    def test_unknown_email_is_an_error(self, db):
        with pytest.raises(cli.CommandError, match="Register it"):
            cli.promote_admin(db, "nobody@example.com")

    def test_unverified_account_is_refused(self, db, make_customer):
        make_customer(email="new@example.com", email_verified=False)

        with pytest.raises(cli.CommandError, match="not verified"):
            cli.promote_admin(db, "new@example.com")

    def test_main_returns_error_code(self, capsys):
        assert cli.main(["promote-admin", "nobody@example.com"]) == 1
        assert "No account" in capsys.readouterr().err


class TestSeedProducts:
    def test_loads_every_product_with_zero_stock(self, db):
        added, skipped = cli.seed_products(db)

        assert len(added) == len(SEED_PRODUCTS) and skipped == []
        products = db.query(Product).all()
        assert {p.stock_quantity for p in products} == {0}
        assert all(p.wholesale_price <= p.retail_price for p in products)

    def test_running_twice_adds_nothing_and_keeps_edits(self, db, make_product):
        make_product(name="toor dal", retail_price=999)

        cli.seed_products(db)
        added, skipped = cli.seed_products(db)

        assert added == []
        assert len(skipped) == len(SEED_PRODUCTS)
        assert db.query(Product).count() == len(SEED_PRODUCTS)
        toor = db.query(Product).filter_by(name="toor dal").one()
        assert float(toor.retail_price) == 999

    def test_seeded_products_appear_on_storefront(self, client, db):
        cli.seed_products(db)

        names = [p["name"] for p in client.get("/api/products/?limit=100").json()]

        assert "Sona Masuri Rice" in names
