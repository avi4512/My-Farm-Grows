from decimal import Decimal

import pytest

from app.models import CartItem


def test_cart_requires_login(client):
    assert client.get("/api/cart").status_code == 401
    assert (
        client.post(
            "/api/cart/items", json={"product_id": 1, "quantity": 1}
        ).status_code
        == 401
    )


def test_new_cart_is_empty(client, make_customer, auth):
    response = client.get("/api/cart", headers=auth(make_customer()))

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert Decimal(response.json()["total"]) == 0


def test_adding_a_product_shows_line_and_total(
    make_customer, make_product, add_to_cart
):
    product = make_product(name="Toor Dal", retail_price=150)

    cart = add_to_cart(make_customer(), product, 2)

    assert len(cart["items"]) == 1
    assert cart["items"][0]["product_name"] == "Toor Dal"
    assert cart["items"][0]["quantity"] == 2
    assert Decimal(cart["items"][0]["subtotal"]) == 300
    assert Decimal(cart["total"]) == 300


def test_total_adds_up_several_products(make_customer, make_product, add_to_cart):
    customer = make_customer()
    add_to_cart(customer, make_product(retail_price="19.99"), 3)

    cart = add_to_cart(customer, make_product(retail_price="0.03"), 1)

    assert Decimal(cart["total"]) == Decimal("60.00")


def test_adding_the_same_product_again_raises_the_quantity(
    make_customer, make_product, add_to_cart
):
    customer = make_customer()
    product = make_product()
    add_to_cart(customer, product, 2)

    cart = add_to_cart(customer, product, 3)

    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 5


@pytest.mark.parametrize("customer_type", ["retail", "wholesale"])
@pytest.mark.parametrize(
    ("quantity", "unit_price"), [(1, 100), (24, 100), (25, 80), (30, 80)]
)
def test_price_depends_on_quantity_not_account_type(
    make_customer, make_product, add_to_cart, customer_type, quantity, unit_price
):
    customer = make_customer(customer_type=customer_type)
    product = make_product(
        retail_price=100, wholesale_price=80, min_wholesale_quantity=25
    )

    cart = add_to_cart(customer, product, quantity)

    assert Decimal(cart["items"][0]["unit_price"]) == unit_price
    assert Decimal(cart["total"]) == unit_price * quantity


def test_changing_quantity_across_the_minimum_changes_the_price(
    client, make_customer, make_product, add_to_cart, auth
):
    customer = make_customer()
    product = make_product(
        retail_price=100, wholesale_price=80, min_wholesale_quantity=25
    )
    item_id = add_to_cart(customer, product, 24)["items"][0]["id"]

    raised = client.patch(
        f"/api/cart/items/{item_id}", json={"quantity": 25}, headers=auth(customer)
    ).json()
    lowered = client.patch(
        f"/api/cart/items/{item_id}", json={"quantity": 24}, headers=auth(customer)
    ).json()

    assert Decimal(raised["total"]) == 2000
    assert Decimal(lowered["total"]) == 2400


def test_cannot_add_more_than_stock(client, make_customer, make_product, auth):
    product = make_product(stock_quantity=3)

    response = client.post(
        "/api/cart/items",
        json={"product_id": product.id, "quantity": 4},
        headers=auth(make_customer()),
    )

    assert response.status_code == 409


def test_repeat_adds_cannot_pass_stock(
    client, make_customer, make_product, add_to_cart, auth
):
    customer = make_customer()
    product = make_product(stock_quantity=3)
    add_to_cart(customer, product, 2)

    response = client.post(
        "/api/cart/items",
        json={"product_id": product.id, "quantity": 2},
        headers=auth(customer),
    )

    assert response.status_code == 409
    assert (
        client.get("/api/cart", headers=auth(customer)).json()["items"][0]["quantity"]
        == 2
    )


def test_cannot_add_unknown_or_inactive_product(
    client, make_customer, make_product, auth
):
    headers = auth(make_customer())
    inactive = make_product(is_active=False)

    for product_id in (inactive.id, 99999):
        response = client.post(
            "/api/cart/items",
            json={"product_id": product_id, "quantity": 1},
            headers=headers,
        )
        assert response.status_code == 404


def test_quantity_must_be_positive(client, make_customer, make_product, auth):
    product = make_product()

    for quantity in (0, -1):
        response = client.post(
            "/api/cart/items",
            json={"product_id": product.id, "quantity": quantity},
            headers=auth(make_customer()),
        )
        assert response.status_code == 422


def test_update_changes_quantity(
    client, make_customer, make_product, add_to_cart, auth
):
    customer = make_customer()
    item_id = add_to_cart(customer, make_product())["items"][0]["id"]

    response = client.patch(
        f"/api/cart/items/{item_id}", json={"quantity": 7}, headers=auth(customer)
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == 7


def test_update_cannot_pass_stock(
    client, make_customer, make_product, add_to_cart, auth
):
    customer = make_customer()
    item_id = add_to_cart(customer, make_product(stock_quantity=3))["items"][0]["id"]

    response = client.patch(
        f"/api/cart/items/{item_id}", json={"quantity": 4}, headers=auth(customer)
    )

    assert response.status_code == 409


def test_remove_deletes_one_line(
    client, make_customer, make_product, add_to_cart, auth
):
    customer = make_customer()
    item_id = add_to_cart(customer, make_product())["items"][0]["id"]
    keep = make_product(name="Keep Me")
    add_to_cart(customer, keep)

    response = client.delete(f"/api/cart/items/{item_id}", headers=auth(customer))

    assert response.status_code == 204
    names = [
        i["product_name"]
        for i in client.get("/api/cart", headers=auth(customer)).json()["items"]
    ]
    assert names == ["Keep Me"]


def test_clear_empties_only_your_own_cart(
    client, db, make_customer, make_product, add_to_cart, auth
):
    mine, other = make_customer(), make_customer()
    product = make_product()
    add_to_cart(mine, product)
    add_to_cart(other, product)

    assert client.delete("/api/cart", headers=auth(mine)).status_code == 204

    assert client.get("/api/cart", headers=auth(mine)).json()["items"] == []
    assert len(client.get("/api/cart", headers=auth(other)).json()["items"]) == 1
    assert db.query(CartItem).count() == 1


def test_cannot_change_another_customers_cart_item(
    client, make_customer, make_product, add_to_cart, auth
):
    owner, intruder = make_customer(), make_customer()
    item_id = add_to_cart(owner, make_product())["items"][0]["id"]
    headers = auth(intruder)

    patched = client.patch(
        f"/api/cart/items/{item_id}", json={"quantity": 9}, headers=headers
    )
    deleted = client.delete(f"/api/cart/items/{item_id}", headers=headers)

    assert patched.status_code == deleted.status_code == 404
    assert (
        client.get("/api/cart", headers=auth(owner)).json()["items"][0]["quantity"] == 1
    )
