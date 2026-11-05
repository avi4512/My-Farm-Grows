from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app.models import InventoryMovement


def adjust(client, product_id, change, headers, reason="Stock count"):
    return client.post(
        f"/api/admin/products/{product_id}/inventory",
        json={"quantity_change": change, "reason": reason},
        headers=headers,
    )


def set_status(client, order_id, status, headers):
    return client.patch(
        f"/api/admin/orders/{order_id}/status",
        json={"status": status},
        headers=headers,
    )


def stock_of(db, product):
    db.expire_all()
    return product.stock_quantity


class TestManualAdjustments:
    def test_admin_can_add_stock_and_it_is_recorded(
        self, client, db, make_customer, make_product, auth
    ):
        admin = make_customer(role="admin")
        product = make_product(stock_quantity=10)

        response = adjust(client, product.id, 5, auth(admin), "New delivery")

        assert response.status_code == 201
        assert stock_of(db, product) == 15
        movement = db.query(InventoryMovement).one()
        assert movement.movement_type == "stock_in"
        assert (movement.previous_stock, movement.new_stock) == (10, 15)
        assert movement.reason == "New delivery"
        assert movement.changed_by_customer_id == admin.id

    def test_admin_can_remove_stock(
        self, client, db, make_customer, make_product, auth
    ):
        product = make_product(stock_quantity=10)

        response = adjust(client, product.id, -4, auth(make_customer(role="admin")))

        assert response.status_code == 201
        assert response.json()["movement_type"] == "stock_out"
        assert stock_of(db, product) == 6

    def test_stock_cannot_go_below_zero(
        self, client, db, make_customer, make_product, auth
    ):
        product = make_product(stock_quantity=3)

        response = adjust(client, product.id, -4, auth(make_customer(role="admin")))

        assert response.status_code == 400
        assert stock_of(db, product) == 3
        assert db.query(InventoryMovement).count() == 0

    def test_zero_change_is_rejected(self, client, make_customer, make_product, auth):
        response = adjust(
            client, make_product().id, 0, auth(make_customer(role="admin"))
        )

        assert response.status_code == 400

    def test_reason_is_required(self, client, make_customer, make_product, auth):
        response = adjust(
            client, make_product().id, 5, auth(make_customer(role="admin")), reason=""
        )

        assert response.status_code == 422

    def test_unknown_product_is_rejected(self, client, make_customer, auth):
        response = adjust(client, 99999, 5, auth(make_customer(role="admin")))

        assert response.status_code == 404

    def test_customers_and_guests_cannot_adjust_stock(
        self, client, db, make_customer, make_product, auth
    ):
        product = make_product(stock_quantity=10)

        assert adjust(client, product.id, 5, auth(make_customer())).status_code == 403
        assert adjust(client, product.id, 5, {}).status_code == 401
        assert stock_of(db, product) == 10


class TestProductCatalogStock:
    def product_body(self, **overrides):
        return {
            "name": "Ragi Flour",
            "category": "Flour",
            "unit": "kg",
            "retail_price": 60,
            "wholesale_price": 50,
            "min_wholesale_quantity": 25,
            "stock_quantity": 40,
            "is_active": True,
        } | overrides

    def test_new_product_records_its_starting_stock(
        self, client, db, make_customer, auth
    ):
        response = client.post(
            "/api/products/",
            json=self.product_body(),
            headers=auth(make_customer(role="admin")),
        )

        assert response.status_code == 201, response.text
        movement = db.query(InventoryMovement).one()
        assert movement.movement_type == "initial_stock"
        assert movement.new_stock == 40

    def test_customers_cannot_create_products(self, client, make_customer, auth):
        response = client.post(
            "/api/products/", json=self.product_body(), headers=auth(make_customer())
        )

        assert response.status_code == 403

    def test_deleting_a_product_with_orders_is_refused_and_keeps_the_history(
        self, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        # A separate client, so a server error is returned rather than raised.
        client = TestClient(fastapi_app, raise_server_exceptions=False)
        customer = make_customer()
        product = make_product()
        add_to_cart(customer, product)
        order = client.post(
            "/api/orders/",
            json={"address_id": make_address(customer)},
            headers=auth(customer),
        ).json()

        response = client.delete(
            f"/api/products/{product.id}", headers=auth(make_customer(role="admin"))
        )

        assert response.status_code == 409
        assert "deactivate" in response.json()["detail"].lower()
        saved = client.get(f"/api/orders/{order['id']}", headers=auth(customer))
        assert saved.status_code == 200
        assert len(saved.json()["items"]) == 1


class TestAdminOrderStatus:
    def order(
        self, client, customer, product, quantity, make_address, add_to_cart, auth
    ):
        add_to_cart(customer, product, quantity)
        response = client.post(
            "/api/orders/",
            json={"address_id": make_address(customer)},
            headers=auth(customer),
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def test_admin_cancel_restores_stock(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        admin = auth(make_customer(role="admin"))
        product = make_product(stock_quantity=10)
        order_id = self.order(
            client, make_customer(), product, 4, make_address, add_to_cart, auth
        )
        assert set_status(client, order_id, "processing", admin).status_code == 200
        assert stock_of(db, product) == 6

        assert set_status(client, order_id, "cancelled", admin).status_code == 200

        assert stock_of(db, product) == 10

    def test_repeating_admin_cancel_restores_stock_once(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        admin = auth(make_customer(role="admin"))
        product = make_product(stock_quantity=10)
        order_id = self.order(
            client, make_customer(), product, 4, make_address, add_to_cart, auth
        )

        assert set_status(client, order_id, "cancelled", admin).status_code == 200
        assert set_status(client, order_id, "cancelled", admin).status_code == 200

        assert stock_of(db, product) == 10

    def test_shipped_order_cannot_be_cancelled(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        admin = auth(make_customer(role="admin"))
        product = make_product(stock_quantity=10)
        order_id = self.order(
            client, make_customer(), product, 4, make_address, add_to_cart, auth
        )
        set_status(client, order_id, "processing", admin)
        set_status(client, order_id, "shipped", admin)

        assert set_status(client, order_id, "cancelled", admin).status_code == 400
        assert stock_of(db, product) == 6

    def test_cancelled_order_cannot_be_reopened(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        admin = auth(make_customer(role="admin"))
        order_id = self.order(
            client, make_customer(), make_product(), 1, make_address, add_to_cart, auth
        )
        set_status(client, order_id, "cancelled", admin)

        assert set_status(client, order_id, "processing", admin).status_code == 400

    def test_customer_cannot_change_order_status(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        order_id = self.order(
            client, customer, make_product(), 1, make_address, add_to_cart, auth
        )

        assert (
            set_status(client, order_id, "delivered", auth(customer)).status_code == 403
        )
