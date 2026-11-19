from .conftest import PASSWORD


def update(client, customer_id, headers, **changes):
    return client.patch(
        f"/api/admin/customers/{customer_id}", json=changes, headers=headers
    )


class TestListingCustomers:
    def test_admin_sees_customers_with_order_counts(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        admin = make_customer(role="admin", name="Admin")
        buyer = make_customer(name="Ravi")
        add_to_cart(buyer, make_product(), 1)
        client.post(
            "/api/orders/",
            json={"address_id": make_address(buyer)},
            headers=auth(buyer),
        )

        response = client.get("/api/admin/customers", headers=auth(admin))

        assert response.status_code == 200
        rows = {row["name"]: row for row in response.json()}
        assert rows["Ravi"]["order_count"] == 1
        assert rows["Admin"]["order_count"] == 0
        assert "hashed_password" not in rows["Ravi"]

    def test_search_and_role_filter(self, client, make_customer, auth):
        admin = make_customer(role="admin", name="Admin")
        make_customer(name="Lakshmi Stores", email="lakshmi@shop.example")
        make_customer(name="Ravi")

        found = client.get(
            "/api/admin/customers?search=lakshmi", headers=auth(admin)
        ).json()
        admins = client.get(
            "/api/admin/customers?role=admin", headers=auth(admin)
        ).json()

        assert [c["name"] for c in found] == ["Lakshmi Stores"]
        assert [c["name"] for c in admins] == ["Admin"]

    def test_customers_cannot_list_accounts(self, client, make_customer, auth):
        response = client.get("/api/admin/customers", headers=auth(make_customer()))

        assert response.status_code == 403


class TestUpdatingCustomers:
    def test_admin_promotes_customer(self, client, db, make_customer, auth):
        admin, customer = make_customer(role="admin"), make_customer()

        response = update(client, customer.id, auth(admin), role="admin")

        assert response.status_code == 200, response.text
        assert response.json()["role"] == "admin"
        assert (
            client.get("/api/admin/orders", headers=auth(customer)).status_code == 200
        )

    def test_admin_changes_account_type(self, client, make_customer, auth):
        admin, customer = make_customer(role="admin"), make_customer()

        response = update(client, customer.id, auth(admin), customer_type="wholesale")

        assert response.json()["customer_type"] == "wholesale"

    def test_deactivated_customer_cannot_log_in_or_use_token(
        self, client, make_customer, auth
    ):
        admin = make_customer(role="admin")
        customer = make_customer()

        update(client, customer.id, auth(admin), is_active=False)

        login = client.post(
            "/api/auth/login", data={"username": customer.email, "password": PASSWORD}
        )
        assert login.status_code == 403
        assert client.get("/api/auth/me", headers=auth(customer)).status_code == 403

    def test_admin_cannot_demote_or_deactivate_themselves(
        self, client, db, make_customer, auth
    ):
        admin = make_customer(role="admin")

        demote = update(client, admin.id, auth(admin), role="customer")
        deactivate = update(client, admin.id, auth(admin), is_active=False)

        assert demote.status_code == 400
        assert deactivate.status_code == 400
        db.expire_all()
        assert admin.role == "admin" and admin.is_active

    def test_admin_can_demote_another_admin(self, client, make_customer, auth):
        admin, other = make_customer(role="admin"), make_customer(role="admin")

        response = update(client, other.id, auth(admin), role="customer")

        assert response.status_code == 200
        assert response.json()["role"] == "customer"

    def test_unknown_fields_and_roles_are_rejected(self, client, make_customer, auth):
        admin, customer = make_customer(role="admin"), make_customer()

        assert update(client, customer.id, auth(admin), role="owner").status_code == 422
        assert (
            update(client, customer.id, auth(admin), email="x@y.z").status_code == 422
        )

    def test_missing_customer_returns_404(self, client, make_customer, auth):
        admin = make_customer(role="admin")

        assert update(client, 9999, auth(admin), role="admin").status_code == 404

    def test_customer_cannot_promote_themselves(self, client, make_customer, auth):
        customer = make_customer()

        response = update(client, customer.id, auth(customer), role="admin")

        assert response.status_code == 403
