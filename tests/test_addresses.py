ADDRESS = {
    "recipient_name": "Test Person",
    "phone": "9876543210",
    "address_line1": "12 Farm Road",
    "city": "Guntur",
    "state": "Andhra Pradesh",
    "postal_code": "522001",
}


def create(client, headers, **overrides):
    return client.post("/api/addresses/", json=ADDRESS | overrides, headers=headers)


def listed(client, headers):
    return client.get("/api/addresses/", headers=headers).json()


def default_ids(client, headers):
    return [a["id"] for a in listed(client, headers) if a["is_default"]]


class TestCreatingAddresses:
    def test_first_address_becomes_the_default(self, client, make_customer, auth):
        customer = make_customer()

        response = create(client, auth(customer))

        assert response.status_code == 201, response.text
        assert response.json()["is_default"] is True
        assert response.json()["country"] == "India"

    def test_later_address_is_not_the_default_unless_asked(
        self, client, make_customer, auth
    ):
        customer = make_customer()
        first = create(client, auth(customer)).json()

        second = create(client, auth(customer), city="Vijayawada").json()

        assert second["is_default"] is False
        assert default_ids(client, auth(customer)) == [first["id"]]

    def test_new_default_replaces_the_old_one(self, client, make_customer, auth):
        customer = make_customer()
        create(client, auth(customer))

        second = create(client, auth(customer), is_default=True).json()

        assert default_ids(client, auth(customer)) == [second["id"]]

    def test_default_address_is_listed_first(self, client, make_customer, auth):
        customer = make_customer()
        first = create(client, auth(customer)).json()
        create(client, auth(customer), city="Vijayawada")

        assert listed(client, auth(customer))[0]["id"] == first["id"]

    def test_short_phone_number_is_rejected(self, client, make_customer, auth):
        response = create(client, auth(make_customer()), phone="12345")

        assert response.status_code == 422

    def test_requires_login(self, client):
        assert client.post("/api/addresses/", json=ADDRESS).status_code == 401


class TestAddressOwnership:
    def test_customers_see_only_their_own_addresses(self, client, make_customer, auth):
        ravi, sita = make_customer(), make_customer()
        create(client, auth(ravi))

        assert listed(client, auth(sita)) == []

    def test_another_customers_address_is_not_found(self, client, make_customer, auth):
        owner, stranger = make_customer(), make_customer()
        address_id = create(client, auth(owner)).json()["id"]
        path = f"/api/addresses/{address_id}"

        assert client.get(path, headers=auth(stranger)).status_code == 404
        assert (
            client.put(
                path, json={"city": "X City"}, headers=auth(stranger)
            ).status_code
            == 404
        )
        assert client.delete(path, headers=auth(stranger)).status_code == 404
        assert client.get(path, headers=auth(owner)).json()["city"] == "Guntur"


class TestUpdatingAddresses:
    def test_update_changes_only_the_given_fields(self, client, make_customer, auth):
        customer = make_customer()
        address_id = create(client, auth(customer)).json()["id"]

        response = client.put(
            f"/api/addresses/{address_id}",
            json={"city": "Tenali", "landmark": "Near temple"},
            headers=auth(customer),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["city"], body["landmark"]) == ("Tenali", "Near temple")
        assert body["address_line1"] == "12 Farm Road"

    def test_required_field_cannot_be_set_to_null(self, client, make_customer, auth):
        customer = make_customer()
        address_id = create(client, auth(customer)).json()["id"]

        response = client.put(
            f"/api/addresses/{address_id}", json={"city": None}, headers=auth(customer)
        )

        assert response.status_code == 422

    def test_making_an_address_default_clears_the_old_default(
        self, client, make_customer, auth
    ):
        customer = make_customer()
        create(client, auth(customer))
        second = create(client, auth(customer), city="Vijayawada").json()

        client.put(
            f"/api/addresses/{second['id']}",
            json={"is_default": True},
            headers=auth(customer),
        )

        assert default_ids(client, auth(customer)) == [second["id"]]


class TestDeletingAddresses:
    def test_deleting_the_default_promotes_another_address(
        self, client, make_customer, auth
    ):
        customer = make_customer()
        first = create(client, auth(customer)).json()
        second = create(client, auth(customer), city="Vijayawada").json()

        response = client.delete(
            f"/api/addresses/{first['id']}", headers=auth(customer)
        )

        assert response.status_code == 204
        assert default_ids(client, auth(customer)) == [second["id"]]

    def test_address_used_by_an_order_cannot_be_deleted(
        self, client, make_customer, make_product, add_to_cart, auth
    ):
        customer = make_customer()
        address_id = create(client, auth(customer)).json()["id"]
        add_to_cart(customer, make_product())
        client.post(
            "/api/orders/",
            json={"address_id": address_id, "payment_method": "cash_on_delivery"},
            headers=auth(customer),
        )

        response = client.delete(f"/api/addresses/{address_id}", headers=auth(customer))

        assert response.status_code == 409
        assert len(listed(client, auth(customer))) == 1
