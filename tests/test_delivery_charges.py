from decimal import Decimal

import pytest

from app.models import Order
from app.services.pricing import get_delivery_charge


def place_order(client, headers, address_id):
    return client.post(
        "/api/orders/",
        json={"address_id": address_id, "payment_method": "cash_on_delivery"},
        headers=headers,
    )


class TestDeliveryChargeRules:
    @pytest.mark.parametrize(
        ("state", "charge"),
        [
            ("Andhra Pradesh", "50.00"),
            ("andhra  pradesh ", "50.00"),
            ("A.P.", "50.00"),
            ("Telangana", "150.00"),
            ("Telengana", "150.00"),
            ("TS", "150.00"),
        ],
    )
    def test_charge_by_state(self, state, charge):
        assert get_delivery_charge(state, Decimal("500.00")) == Decimal(charge)

    def test_states_outside_ap_and_telangana_are_not_served(self):
        assert get_delivery_charge("Karnataka", Decimal("500.00")) is None

    @pytest.mark.parametrize("state", ["Andhra Pradesh", "Telangana"])
    def test_delivery_is_free_above_2000(self, state):
        assert get_delivery_charge(state, Decimal("2000.01")) == Decimal("0.00")

    def test_delivery_is_charged_at_exactly_2000(self):
        assert get_delivery_charge("Telangana", Decimal("2000.00")) == Decimal("150.00")


class TestOrderDeliveryCharge:
    def test_telangana_order_adds_150(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        add_to_cart(customer, make_product(retail_price=100), 3)
        address_id = make_address(customer, state="Telangana", city="Hyderabad")

        order = place_order(client, auth(customer), address_id).json()

        assert Decimal(order["delivery_charge"]) == Decimal("150.00")
        assert Decimal(order["total_amount"]) == Decimal("450.00")

    def test_order_above_2000_has_free_delivery(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        add_to_cart(customer, make_product(retail_price=1001), 2)

        order = place_order(client, auth(customer), make_address(customer)).json()

        assert Decimal(order["delivery_charge"]) == Decimal("0.00")
        assert Decimal(order["total_amount"]) == Decimal("2002.00")

    def test_free_delivery_is_measured_after_the_offer_discount(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        add_to_cart(customer, make_product(retail_price=5100), 1)

        order = place_order(client, auth(customer), make_address(customer)).json()

        assert Decimal(order["discount_amount"]) == Decimal("510.00")
        assert Decimal(order["delivery_charge"]) == Decimal("0.00")
        assert Decimal(order["total_amount"]) == Decimal("4590.00")

    def test_order_to_another_state_is_rejected_and_keeps_the_cart(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        product = make_product(stock_quantity=10)
        add_to_cart(customer, product, 2)
        address_id = make_address(customer, state="Karnataka", city="Bengaluru")

        response = place_order(client, auth(customer), address_id)

        assert response.status_code == 400
        assert "Andhra Pradesh and Telangana" in response.json()["detail"]
        assert db.query(Order).count() == 0
        db.expire_all()
        assert product.stock_quantity == 10
        assert len(client.get("/api/cart", headers=auth(customer)).json()["items"]) == 1
