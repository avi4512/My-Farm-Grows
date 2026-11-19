"""Admin payment endpoints used by the new admin Payments screen."""

import pytest


@pytest.fixture
def online_order(client, make_customer, make_product, make_address, add_to_cart, auth):
    """A placed online order with one pending payment transaction."""
    customer = make_customer()
    add_to_cart(customer, make_product(retail_price=200), 2)
    order = client.post(
        "/api/orders/",
        json={"address_id": make_address(customer), "payment_method": "online"},
        headers=auth(customer),
    ).json()
    payment = client.post(
        "/api/payments/",
        json={"order_id": order["id"], "payment_method": "online"},
        headers=auth(customer),
    ).json()
    return {"customer": customer, "order": order, "payment": payment}


def set_status(client, payment_id, headers, **body):
    return client.patch(
        f"/api/payments/admin/{payment_id}/status", json=body, headers=headers
    )


def test_admin_sees_all_payments(client, make_customer, auth, online_order):
    admin = make_customer(role="admin")

    response = client.get("/api/payments/admin/history", headers=auth(admin))

    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == [online_order["payment"]["id"]]
    assert response.json()[0]["status"] == "pending"


def test_customer_cannot_see_admin_history(client, auth, online_order):
    response = client.get(
        "/api/payments/admin/history", headers=auth(online_order["customer"])
    )

    assert response.status_code == 403


def test_marking_paid_updates_the_order(client, make_customer, auth, online_order):
    admin = make_customer(role="admin")

    response = set_status(
        client, online_order["payment"]["id"], auth(admin), status="paid"
    )

    assert response.status_code == 200
    order = client.get(
        f"/api/orders/{online_order['order']['id']}",
        headers=auth(online_order["customer"]),
    ).json()
    assert order["payment_status"] == "paid"


def test_marking_failed_keeps_the_reason(client, make_customer, auth, online_order):
    admin = make_customer(role="admin")

    response = set_status(
        client,
        online_order["payment"]["id"],
        auth(admin),
        status="failed",
        failure_reason="Bank declined",
    )

    assert response.json()["status"] == "failed"
    assert response.json()["failure_reason"] == "Bank declined"


def test_finished_payment_cannot_change_again(
    client, make_customer, auth, online_order
):
    admin = make_customer(role="admin")
    set_status(client, online_order["payment"]["id"], auth(admin), status="paid")

    response = set_status(
        client, online_order["payment"]["id"], auth(admin), status="failed"
    )

    assert response.status_code == 400


def test_reconciliation_flags_order_paid_without_transaction(
    client, db, make_customer, auth, online_order
):
    from app.models import Order

    admin = make_customer(role="admin")
    order = db.get(Order, online_order["order"]["id"])
    order.payment_status = "paid"  # set by hand, with no paid transaction
    db.commit()

    report = client.get(
        "/api/payments/admin/reconciliation", headers=auth(admin)
    ).json()

    assert report["discrepancy_count"] == 1
    assert (
        report["discrepancies"][0]["issue"]
        == "order_paid_without_successful_transaction"
    )


def test_reconciliation_is_clean_after_proper_payment(
    client, make_customer, auth, online_order
):
    admin = make_customer(role="admin")
    set_status(client, online_order["payment"]["id"], auth(admin), status="paid")

    report = client.get(
        "/api/payments/admin/reconciliation", headers=auth(admin)
    ).json()

    assert report["discrepancy_count"] == 0
