from app.models import InventoryMovement, Product

NEW_PRODUCT = {
    "name": "Toor Dal",
    "category": "Pulses",
    "unit": "kg",
    "retail_price": 150,
    "wholesale_price": 136,
    "min_wholesale_quantity": 25,
    "stock_quantity": 40,
    "image_url": "images/toor-dal.jpg",
}


def create(client, headers, **overrides):
    return client.post("/api/products/", json=NEW_PRODUCT | overrides, headers=headers)


class TestCreatingProducts:
    def test_admin_creates_product_with_image_and_opening_stock(
        self, client, db, make_customer, auth
    ):
        admin = make_customer(role="admin")

        response = create(client, auth(admin))

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["image_url"] == "images/toor-dal.jpg"
        assert body["is_active"] is True
        movement = db.query(InventoryMovement).one()
        assert movement.movement_type == "initial_stock"
        assert movement.quantity_change == 40

    def test_product_can_be_created_hidden(self, client, make_customer, auth):
        admin = make_customer(role="admin")

        response = create(client, auth(admin), is_active=False)

        assert response.status_code == 201
        assert response.json()["is_active"] is False

    def test_customer_cannot_create_product(self, client, db, make_customer, auth):
        response = create(client, auth(make_customer()))

        assert response.status_code == 403
        assert db.query(Product).count() == 0

    def test_wholesale_price_above_retail_is_rejected(
        self, client, make_customer, auth
    ):
        admin = make_customer(role="admin")

        response = create(client, auth(admin), retail_price=100, wholesale_price=120)

        assert response.status_code == 422

    def test_https_image_url_is_accepted(self, client, make_customer, auth):
        admin = make_customer(role="admin")
        url = "https://cdn.example.com/products/dal.jpg"

        response = create(client, auth(admin), image_url=url)

        assert response.status_code == 201
        assert response.json()["image_url"] == url

    def test_blank_image_url_is_stored_as_none(self, client, make_customer, auth):
        admin = make_customer(role="admin")

        response = create(client, auth(admin), image_url="   ")

        assert response.status_code == 201
        assert response.json()["image_url"] is None

    def test_unsafe_image_values_are_rejected(self, client, make_customer, auth):
        admin = make_customer(role="admin")
        unsafe = [
            "javascript:alert(1)",
            "data:image/png;base64,AAAA",
            "images/../../app/core/config.py",
            '"><script>alert(1)</script>',
            "images/notes.txt",
        ]

        for value in unsafe:
            response = create(client, auth(admin), image_url=value)
            assert response.status_code == 422, value


class TestUpdatingProducts:
    def test_admin_updates_details_and_image(
        self, client, db, make_customer, make_product, auth
    ):
        admin = make_customer(role="admin")
        product = make_product(name="Old name")

        response = client.put(
            f"/api/products/{product.id}",
            json={
                "name": "Sona Masuri Rice",
                "image_url": "images/sona-masoori-rice.jpg",
            },
            headers=auth(admin),
        )

        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Sona Masuri Rice"
        assert response.json()["image_url"] == "images/sona-masoori-rice.jpg"

    def test_image_can_be_removed(self, client, make_customer, make_product, auth):
        admin = make_customer(role="admin")
        product = make_product(image_url="images/toor-dal.jpg")

        response = client.put(
            f"/api/products/{product.id}", json={"image_url": None}, headers=auth(admin)
        )

        assert response.status_code == 200
        assert response.json()["image_url"] is None

    def test_partial_price_update_cannot_put_wholesale_above_retail(
        self, client, db, make_customer, make_product, auth
    ):
        admin = make_customer(role="admin")
        product = make_product(retail_price=100, wholesale_price=80)

        response = client.put(
            f"/api/products/{product.id}",
            json={"wholesale_price": 150},
            headers=auth(admin),
        )

        assert response.status_code == 400
        db.expire_all()
        assert float(product.wholesale_price) == 80

    def test_hidden_product_leaves_the_storefront_but_not_the_admin_list(
        self, client, make_customer, make_product, auth
    ):
        admin = make_customer(role="admin")
        product = make_product()

        client.put(
            f"/api/products/{product.id}",
            json={"is_active": False},
            headers=auth(admin),
        )

        storefront = client.get("/api/products/").json()
        admin_list = client.get("/api/products/?active_only=false").json()
        assert product.id not in [p["id"] for p in storefront]
        assert product.id in [p["id"] for p in admin_list]
        assert client.get(f"/api/products/{product.id}").status_code == 404


class TestDeletingProducts:
    def test_unused_product_can_be_deleted(
        self, client, db, make_customer, make_product, auth
    ):
        admin = make_customer(role="admin")
        product = make_product()

        response = client.delete(f"/api/products/{product.id}", headers=auth(admin))

        assert response.status_code == 204
        assert db.query(Product).count() == 0

    def test_product_with_orders_cannot_be_deleted(
        self, client, db, make_customer, make_product, make_address, add_to_cart, auth
    ):
        admin, customer = make_customer(role="admin"), make_customer()
        product = make_product()
        add_to_cart(customer, product, 1)
        client.post(
            "/api/orders/",
            json={"address_id": make_address(customer)},
            headers=auth(customer),
        )

        response = client.delete(f"/api/products/{product.id}", headers=auth(admin))

        assert response.status_code == 409
        assert "Deactivate" in response.json()["detail"]
