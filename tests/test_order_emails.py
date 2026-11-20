import pytest

import app.services.email as email_service


@pytest.fixture
def placed_order(
    client, make_customer, make_product, make_address, add_to_cart, auth, outbox
):
    """A pending cash-on-delivery order, with the confirmation email cleared."""
    customer = make_customer(name="Ravi", email="ravi@example.com")
    add_to_cart(customer, make_product())
    response = client.post(
        "/api/orders/",
        json={
            "address_id": make_address(customer),
            "payment_method": "cash_on_delivery",
        },
        headers=auth(customer),
    )
    assert response.status_code == 201, response.text
    outbox.clear()
    return customer, response.json()["id"]


@pytest.fixture
def admin(make_customer):
    return make_customer(role="admin", name="Admin")


def set_order_status(client, headers, order_id, new_status):
    response = client.patch(
        f"/api/admin/orders/{order_id}/status",
        json={"status": new_status},
        headers=headers,
    )
    assert response.status_code == 200, response.text


def create_delivery(client, headers, order_id, **details):
    response = client.post(
        "/api/admin/deliveries", json={"order_id": order_id, **details}, headers=headers
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def set_delivery_status(client, headers, delivery_id, new_status):
    response = client.patch(
        f"/api/admin/deliveries/{delivery_id}",
        json={"status": new_status},
        headers=headers,
    )
    assert response.status_code == 200, response.text


class TestOrderStatusEmails:
    def test_shipping_an_order_emails_the_customer(
        self, client, auth, admin, placed_order, outbox
    ):
        _, order_id = placed_order
        set_order_status(client, auth(admin), order_id, "processing")
        assert outbox == []

        set_order_status(client, auth(admin), order_id, "shipped")

        [email] = outbox
        assert email["to"] == "ravi@example.com"
        assert (
            email["subject"] == f"Your My Farm Grow order #{order_id} has been shipped"
        )
        assert "Hi Ravi" in email["html"]

    def test_delivering_an_order_emails_the_customer(
        self, client, auth, admin, placed_order, outbox
    ):
        _, order_id = placed_order
        for new_status in ("processing", "shipped", "delivered"):
            set_order_status(client, auth(admin), order_id, new_status)

        assert [e["subject"].rsplit(" ", 1)[-1] for e in outbox] == [
            "shipped",
            "delivered",
        ]

    def test_admin_cancelling_an_order_emails_the_customer(
        self, client, auth, admin, placed_order, outbox
    ):
        _, order_id = placed_order

        set_order_status(client, auth(admin), order_id, "cancelled")

        [email] = outbox
        assert "has been cancelled" in email["subject"]
        assert "refund" not in email["html"]

    def test_customer_cancelling_an_order_gets_an_email(
        self, client, auth, placed_order, outbox
    ):
        customer, order_id = placed_order

        response = client.post(f"/api/orders/{order_id}/cancel", headers=auth(customer))

        assert response.status_code == 200, response.text
        [email] = outbox
        assert email["to"] == "ravi@example.com"
        assert "has been cancelled" in email["subject"]

    def test_repeating_the_same_status_sends_no_second_email(
        self, client, auth, admin, placed_order, outbox
    ):
        _, order_id = placed_order
        set_order_status(client, auth(admin), order_id, "cancelled")
        set_order_status(client, auth(admin), order_id, "cancelled")

        assert len(outbox) == 1

    def test_a_failed_email_does_not_undo_the_status_change(
        self, client, db, monkeypatch, auth, admin, placed_order
    ):
        async def failing_send(*_args):
            raise RuntimeError("Email provider is down")

        monkeypatch.setattr(email_service, "send_email", failing_send)
        _, order_id = placed_order

        set_order_status(client, auth(admin), order_id, "cancelled")

        response = client.get("/api/admin/orders", headers=auth(admin))
        assert response.json()[0]["status"] == "cancelled"


class TestDeliveryEmails:
    def test_shipping_through_the_delivery_includes_tracking_details(
        self, client, auth, admin, placed_order, outbox
    ):
        _, order_id = placed_order
        delivery_id = create_delivery(
            client,
            auth(admin),
            order_id,
            delivery_partner="Farm Van",
            estimated_delivery_date="2026-12-01",
        )

        set_delivery_status(client, auth(admin), delivery_id, "shipped")

        [email] = outbox
        assert "has been shipped" in email["subject"]
        assert "Farm Van" in email["html"]
        assert f"MFG-ORD-{order_id}" in email["html"]
        assert "01 Dec 2026" in email["html"]

    def test_out_for_delivery_sends_its_own_email(
        self, client, auth, admin, placed_order, outbox
    ):
        _, order_id = placed_order
        delivery_id = create_delivery(client, auth(admin), order_id)

        set_delivery_status(client, auth(admin), delivery_id, "shipped")
        set_delivery_status(client, auth(admin), delivery_id, "out_for_delivery")
        set_delivery_status(client, auth(admin), delivery_id, "delivered")

        assert [e["subject"].split(" order ")[1].split(" ", 1)[1] for e in outbox] == [
            "has been shipped",
            "is out for delivery",
            "has been delivered",
        ]

    def test_shipping_the_order_then_the_delivery_emails_once(
        self, client, auth, admin, placed_order, outbox
    ):
        _, order_id = placed_order
        delivery_id = create_delivery(client, auth(admin), order_id)
        set_order_status(client, auth(admin), order_id, "processing")
        set_order_status(client, auth(admin), order_id, "shipped")

        set_delivery_status(client, auth(admin), delivery_id, "shipped")

        assert len(outbox) == 1

    def test_packing_sends_no_email(self, client, auth, admin, placed_order, outbox):
        _, order_id = placed_order
        delivery_id = create_delivery(client, auth(admin), order_id)

        set_delivery_status(client, auth(admin), delivery_id, "packed")

        assert outbox == []
