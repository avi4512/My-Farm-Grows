from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from fastapi.testclient import TestClient

import app.api.routes.order as order_routes
from app.main import app as fastapi_app
from app.models import CartItem, InventoryMovement, Order


def place_order(client, headers, address_id, payment_method="cash_on_delivery"):
    return client.post(
        "/api/orders/",
        json={"address_id": address_id, "payment_method": payment_method},
        headers=headers,
    )


def stock_of(db, product):
    db.expire_all()
    return product.stock_quantity


def movements(db, movement_type):
    db.expire_all()
    return db.query(InventoryMovement).filter_by(movement_type=movement_type).all()


class TestPlacingAnOrder:
    def test_order_deducts_stock_clears_cart_and_totals_correctly(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        rice = make_product(name="Rice", retail_price=120, stock_quantity=10)
        dal = make_product(name="Dal", retail_price="150.50", stock_quantity=5)
        add_to_cart(customer, rice, 2)
        add_to_cart(customer, dal, 1)

        response = place_order(client, auth(customer), make_address(customer))

        assert response.status_code == 201, response.text
        order = response.json()
        assert Decimal(order["total_amount"]) == Decimal("390.50")
        assert order["status"] == "pending"
        assert order["payment_status"] == "pending"
        assert {i["product_name"]: i["quantity"] for i in order["items"]} == {
            "Rice": 2,
            "Dal": 1,
        }
        assert stock_of(db, rice) == 8
        assert stock_of(db, dal) == 4
        assert db.query(CartItem).count() == 0

    def test_order_records_a_stock_movement_for_each_product(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        product = make_product(stock_quantity=10)
        add_to_cart(customer, product, 3)

        order = place_order(client, auth(customer), make_address(customer)).json()

        [movement] = movements(db, "order_deduction")
        assert movement.product_id == product.id
        assert movement.quantity_change == -3
        assert (movement.previous_stock, movement.new_stock) == (10, 7)
        assert movement.order_id == order["id"]
        assert movement.changed_by_customer_id == customer.id

    def test_order_sends_a_confirmation_email(
        self,
        client,
        make_customer,
        make_product,
        make_address,
        add_to_cart,
        auth,
        outbox,
    ):
        customer = make_customer(email="ravi@example.com")
        add_to_cart(customer, make_product())

        order = place_order(client, auth(customer), make_address(customer)).json()

        assert outbox[-1]["to"] == "ravi@example.com"
        assert f"#{order['id']}" in outbox[-1]["subject"]

    def test_order_survives_an_email_failure(
        self,
        client,
        db,
        monkeypatch,
        make_customer,
        make_product,
        make_address,
        add_to_cart,
        auth,
    ):
        async def failing_send(*_args):
            raise RuntimeError("Email provider is down")

        monkeypatch.setattr(order_routes, "send_email", failing_send)
        customer = make_customer()
        product = make_product(stock_quantity=10)
        add_to_cart(customer, product, 2)

        response = place_order(client, auth(customer), make_address(customer))

        assert response.status_code == 201
        assert stock_of(db, product) == 8

    def test_order_keeps_its_address_after_the_address_changes(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        address_id = make_address(customer, city="Guntur")
        add_to_cart(customer, make_product())
        order = place_order(client, auth(customer), address_id).json()

        updated = client.put(
            f"/api/addresses/{address_id}",
            json={"city": "Tirupati"},
            headers=auth(customer),
        )
        assert updated.status_code == 200, updated.text

        saved = client.get(f"/api/orders/{order['id']}", headers=auth(customer)).json()
        assert saved["city"] == "Guntur"

    def test_order_total_matches_the_cart_for_a_retail_customer(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        cart = add_to_cart(customer, make_product(retail_price=100), 2)

        order = place_order(client, auth(customer), make_address(customer)).json()

        assert Decimal(order["total_amount"]) == Decimal(cart["total"])

    def test_order_total_matches_the_cart_for_a_wholesale_customer(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer(customer_type="wholesale")
        product = make_product(
            retail_price=100, wholesale_price=80, min_wholesale_quantity=25
        )
        cart = add_to_cart(customer, product, 2)

        order = place_order(client, auth(customer), make_address(customer)).json()

        assert Decimal(order["total_amount"]) == Decimal(cart["total"])

    def test_order_total_matches_the_cart_for_a_large_retail_order(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        product = make_product(
            retail_price=100, wholesale_price=80, min_wholesale_quantity=25
        )
        cart = add_to_cart(customer, product, 30)

        order = place_order(client, auth(customer), make_address(customer)).json()

        assert Decimal(order["total_amount"]) == Decimal(cart["total"])


class TestRejectedOrders:
    def test_order_requires_login(self, client):
        assert client.post("/api/orders/", json={"address_id": 1}).status_code == 401

    def test_empty_cart_is_rejected(
        self, client, db, make_customer, make_address, auth
    ):
        customer = make_customer()

        response = place_order(client, auth(customer), make_address(customer))

        assert response.status_code == 400
        assert db.query(Order).count() == 0

    def test_another_customers_address_is_rejected(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer, other = make_customer(), make_customer()
        product = make_product(stock_quantity=10)
        add_to_cart(customer, product, 2)

        response = place_order(client, auth(customer), make_address(other))

        assert response.status_code == 404
        assert stock_of(db, product) == 10
        assert db.query(Order).count() == 0

    def test_unknown_payment_method_is_rejected(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        add_to_cart(customer, make_product())

        response = place_order(client, auth(customer), make_address(customer), "free")

        assert response.status_code == 422

    def test_one_short_item_rejects_the_whole_order(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        plenty = make_product(stock_quantity=10)
        short = make_product(stock_quantity=5)
        add_to_cart(customer, plenty, 2)
        add_to_cart(customer, short, 5)
        short.stock_quantity = 4
        db.commit()

        response = place_order(client, auth(customer), make_address(customer))

        assert response.status_code == 400
        assert stock_of(db, plenty) == 10
        assert stock_of(db, short) == 4
        assert db.query(Order).count() == 0
        assert db.query(CartItem).count() == 2
        assert movements(db, "order_deduction") == []

    def test_product_deactivated_after_adding_rejects_the_order(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        product = make_product(stock_quantity=10)
        add_to_cart(customer, product)
        product.is_active = False
        db.commit()

        response = place_order(client, auth(customer), make_address(customer))

        assert response.status_code == 400
        assert stock_of(db, product) == 10
        assert db.query(Order).count() == 0


class TestViewingOrders:
    def test_customers_see_only_their_own_orders(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        owner, other = make_customer(), make_customer()
        add_to_cart(owner, make_product())
        order = place_order(client, auth(owner), make_address(owner)).json()

        assert client.get("/api/orders/", headers=auth(other)).json() == []
        assert [
            o["id"] for o in client.get("/api/orders/", headers=auth(owner)).json()
        ] == [order["id"]]
        assert (
            client.get(f"/api/orders/{order['id']}", headers=auth(other)).status_code
            == 404
        )


class TestCancelling:
    def ordered(
        self, client, customer, product, quantity, make_address, add_to_cart, auth
    ):
        add_to_cart(customer, product, quantity)
        response = place_order(client, auth(customer), make_address(customer))
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def test_cancelling_restores_stock(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        product = make_product(stock_quantity=10)
        order_id = self.ordered(
            client, customer, product, 4, make_address, add_to_cart, auth
        )
        assert stock_of(db, product) == 6

        response = client.post(f"/api/orders/{order_id}/cancel", headers=auth(customer))

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert stock_of(db, product) == 10
        [movement] = movements(db, "order_cancellation_restock")
        assert movement.quantity_change == 4
        assert movement.order_id == order_id

    def test_cancelling_twice_restores_stock_once(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        product = make_product(stock_quantity=10)
        order_id = self.ordered(
            client, customer, product, 4, make_address, add_to_cart, auth
        )
        url = f"/api/orders/{order_id}/cancel"

        assert client.post(url, headers=auth(customer)).status_code == 200
        assert client.post(url, headers=auth(customer)).status_code == 400

        assert stock_of(db, product) == 10

    def test_another_customer_cannot_cancel(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        owner, other = make_customer(), make_customer()
        product = make_product(stock_quantity=10)
        order_id = self.ordered(
            client, owner, product, 4, make_address, add_to_cart, auth
        )

        response = client.post(f"/api/orders/{order_id}/cancel", headers=auth(other))

        assert response.status_code == 404
        assert stock_of(db, product) == 6

    def test_customer_cannot_cancel_once_processing(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        admin = make_customer(role="admin")
        product = make_product(stock_quantity=10)
        order_id = self.ordered(
            client, customer, product, 4, make_address, add_to_cart, auth
        )
        client.patch(
            f"/api/admin/orders/{order_id}/status",
            json={"status": "processing"},
            headers=auth(admin),
        )

        response = client.post(f"/api/orders/{order_id}/cancel", headers=auth(customer))

        assert response.status_code == 400
        assert stock_of(db, product) == 6


class TestSimultaneousRequests:
    """Each request runs in its own thread with its own database connection."""

    def run_together(self, requests):
        barrier = Barrier(len(requests))

        def run(request):
            barrier.wait(timeout=10)
            return request(TestClient(fastapi_app))

        with ThreadPoolExecutor(len(requests)) as pool:
            return [
                f.result(timeout=30) for f in [pool.submit(run, r) for r in requests]
            ]

    def test_two_customers_cannot_both_buy_the_last_unit(
        self, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        product = make_product(stock_quantity=1)
        requests = []
        for customer in (make_customer(), make_customer()):
            add_to_cart(customer, product, 1)
            headers, address_id = auth(customer), make_address(customer)
            requests.append(lambda c, h=headers, a=address_id: place_order(c, h, a))

        responses = self.run_together(requests)

        assert sorted(r.status_code for r in responses) == [201, 400]
        assert stock_of(db, product) == 0
        assert db.query(Order).count() == 1

    def test_stock_stays_correct_when_many_customers_order_at_once(
        self, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        product = make_product(stock_quantity=20)
        requests = []
        for customer in [make_customer() for _ in range(6)]:
            add_to_cart(customer, product, 3)
            headers, address_id = auth(customer), make_address(customer)
            requests.append(lambda c, h=headers, a=address_id: place_order(c, h, a))

        responses = self.run_together(requests)

        assert [r.status_code for r in responses] == [201] * 6
        assert stock_of(db, product) == 2

    def test_cancelling_at_the_same_moment_restores_stock_once(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        product = make_product(stock_quantity=10)
        add_to_cart(customer, product, 4)
        order_id = place_order(client, auth(customer), make_address(customer)).json()[
            "id"
        ]
        headers = auth(customer)
        url = f"/api/orders/{order_id}/cancel"

        responses = self.run_together(
            [
                lambda c: c.post(url, headers=headers),
                lambda c: c.post(url, headers=headers),
            ]
        )

        assert sorted(r.status_code for r in responses) == [200, 400]
        assert stock_of(db, product) == 10
