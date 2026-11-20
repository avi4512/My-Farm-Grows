import pytest


@pytest.fixture
def admin(make_customer):
    return make_customer(role="admin", name="Admin")


@pytest.fixture
def order_id(client, make_customer, make_product, make_address, add_to_cart, auth):
    customer = make_customer()
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
    return response.json()["id"]


def create_delivery(client, headers, order_id, **details):
    return client.post(
        "/api/admin/deliveries", json={"order_id": order_id, **details}, headers=headers
    )


def update_delivery(client, headers, delivery_id, **changes):
    return client.patch(
        f"/api/admin/deliveries/{delivery_id}", json=changes, headers=headers
    )


def order_status(client, headers, order_id):
    orders = client.get("/api/admin/orders", headers=headers).json()
    return next(o["status"] for o in orders if o["id"] == order_id)


class TestCreatingDeliveries:
    def test_delivery_gets_a_tracking_number_from_the_order(
        self, client, auth, admin, order_id
    ):
        response = create_delivery(
            client,
            auth(admin),
            order_id,
            delivery_partner="Farm Van",
            estimated_delivery_date="2026-12-01",
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["tracking_number"] == f"MFG-ORD-{order_id}"
        assert body["status"] == "pending"
        assert body["delivery_partner"] == "Farm Van"
        assert body["estimated_delivery_date"] == "2026-12-01"

    def test_an_order_gets_only_one_delivery(self, client, auth, admin, order_id):
        create_delivery(client, auth(admin), order_id)

        response = create_delivery(client, auth(admin), order_id)

        assert response.status_code == 409
        assert len(client.get("/api/admin/deliveries", headers=auth(admin)).json()) == 1

    def test_cancelled_order_gets_no_delivery(self, client, auth, admin, order_id):
        client.patch(
            f"/api/admin/orders/{order_id}/status",
            json={"status": "cancelled"},
            headers=auth(admin),
        )

        response = create_delivery(client, auth(admin), order_id)

        assert response.status_code == 409

    def test_unknown_order_is_not_found(self, client, auth, admin):
        assert create_delivery(client, auth(admin), 999).status_code == 404

    def test_customers_cannot_manage_deliveries(
        self, client, auth, make_customer, order_id
    ):
        customer = make_customer()

        assert create_delivery(client, auth(customer), order_id).status_code == 403
        assert (
            client.get("/api/admin/deliveries", headers=auth(customer)).status_code
            == 403
        )


class TestDeliveryProgress:
    @pytest.mark.parametrize(
        ("delivery_status", "expected_order_status"),
        [
            ("packed", "processing"),
            ("shipped", "shipped"),
            ("out_for_delivery", "shipped"),
            ("delivered", "delivered"),
        ],
    )
    def test_delivery_progress_moves_the_order_forward(
        self, client, auth, admin, order_id, delivery_status, expected_order_status
    ):
        delivery_id = create_delivery(client, auth(admin), order_id).json()["id"]

        response = update_delivery(
            client, auth(admin), delivery_id, status=delivery_status
        )

        assert response.status_code == 200, response.text
        assert order_status(client, auth(admin), order_id) == expected_order_status

    def test_delivered_is_final(self, client, auth, admin, order_id):
        delivery_id = create_delivery(client, auth(admin), order_id).json()["id"]
        update_delivery(client, auth(admin), delivery_id, status="delivered")

        response = update_delivery(client, auth(admin), delivery_id, status="shipped")

        assert response.status_code == 400
        assert order_status(client, auth(admin), order_id) == "delivered"

    def test_failed_delivery_can_be_retried(self, client, auth, admin, order_id):
        delivery_id = create_delivery(client, auth(admin), order_id).json()["id"]
        update_delivery(client, auth(admin), delivery_id, status="failed")

        response = update_delivery(client, auth(admin), delivery_id, status="packed")

        assert response.status_code == 200
        assert response.json()["status"] == "packed"

    def test_failed_delivery_does_not_change_the_order(
        self, client, auth, admin, order_id
    ):
        delivery_id = create_delivery(client, auth(admin), order_id).json()["id"]

        update_delivery(client, auth(admin), delivery_id, status="failed")

        assert order_status(client, auth(admin), order_id) == "pending"

    def test_status_cannot_be_set_to_null(self, client, auth, admin, order_id):
        delivery_id = create_delivery(client, auth(admin), order_id).json()["id"]

        response = update_delivery(client, auth(admin), delivery_id, status=None)

        assert response.status_code == 422

    def test_details_can_change_without_a_status(self, client, auth, admin, order_id):
        delivery_id = create_delivery(client, auth(admin), order_id).json()["id"]

        response = update_delivery(
            client, auth(admin), delivery_id, delivery_partner="India Post"
        )

        assert response.status_code == 200
        assert response.json()["delivery_partner"] == "India Post"
        assert response.json()["status"] == "pending"

    def test_unknown_delivery_is_not_found(self, client, auth, admin):
        response = update_delivery(client, auth(admin), 999, status="packed")

        assert response.status_code == 404
