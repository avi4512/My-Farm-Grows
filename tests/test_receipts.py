from fpdf import FPDF

import app.services.receipt as receipt_service


def place_order(client, headers, address_id):
    response = client.post(
        "/api/orders/",
        json={"address_id": address_id, "payment_method": "cash_on_delivery"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def receipt_text(monkeypatch):
    """Capture the text written to the PDF, since the output is compressed."""
    written: list[str] = []
    original_cell, original_multi_cell = FPDF.cell, FPDF.multi_cell

    def cell(self, w=None, h=None, text="", *args, **kwargs):
        written.append(str(text))
        return original_cell(self, w, h, text, *args, **kwargs)

    def multi_cell(self, w, h=None, text="", *args, **kwargs):
        written.append(str(text))
        return original_multi_cell(self, w, h, text, *args, **kwargs)

    monkeypatch.setattr(receipt_service.FPDF, "cell", cell)
    monkeypatch.setattr(receipt_service.FPDF, "multi_cell", multi_cell)
    return written


class TestOrderReceipt:
    def test_customer_downloads_a_pdf_receipt(
        self,
        client,
        monkeypatch,
        make_customer,
        make_product,
        make_address,
        add_to_cart,
        auth,
    ):
        written = receipt_text(monkeypatch)
        customer = make_customer(email="ravi@example.com")
        add_to_cart(customer, make_product(name="Sona Masoori", retail_price=120), 2)
        order_id = place_order(client, auth(customer), make_address(customer))

        response = client.get(f"/api/orders/{order_id}/receipt", headers=auth(customer))

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert (
            f"myfarmgrow-receipt-{order_id}.pdf"
            in (response.headers["content-disposition"])
        )
        assert response.content.startswith(b"%PDF")
        assert f"#{order_id}" in written
        assert "Sona Masoori" in written
        assert "Rs. 240.00" in written
        assert "Rs. 50.00" in written
        assert "Rs. 290.00" in written
        assert "Cash on delivery - Due on delivery" in written
        assert "ravi@example.com" in written

    def test_receipt_shows_the_offer_discount(
        self,
        client,
        monkeypatch,
        make_customer,
        make_product,
        make_address,
        add_to_cart,
        auth,
    ):
        written = receipt_text(monkeypatch)
        customer = make_customer()
        add_to_cart(customer, make_product(retail_price=1000), 6)
        order_id = place_order(client, auth(customer), make_address(customer))

        client.get(f"/api/orders/{order_id}/receipt", headers=auth(customer))

        assert "Offer discount" in written
        assert "Rs. 6,000.00" in written
        assert "- Rs. 600.00" in written
        assert "Free" in written
        assert "Rs. 5,400.00" in written

    def test_another_customer_cannot_download_the_receipt(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        owner, stranger = make_customer(), make_customer()
        add_to_cart(owner, make_product())
        order_id = place_order(client, auth(owner), make_address(owner))

        response = client.get(f"/api/orders/{order_id}/receipt", headers=auth(stranger))

        assert response.status_code == 404

    def test_cancelled_order_has_no_receipt(
        self, client, make_customer, make_product, make_address, add_to_cart, auth
    ):
        customer = make_customer()
        add_to_cart(customer, make_product())
        order_id = place_order(client, auth(customer), make_address(customer))
        client.post(f"/api/orders/{order_id}/cancel", headers=auth(customer))

        response = client.get(f"/api/orders/{order_id}/receipt", headers=auth(customer))

        assert response.status_code == 400

    def test_receipt_requires_login(self, client):
        assert client.get("/api/orders/1/receipt").status_code == 401
