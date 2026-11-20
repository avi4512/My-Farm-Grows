"""Online payment through Razorpay, with the Razorpay API replaced by a fake."""

import hashlib
import hmac
import json
from decimal import Decimal

import pytest

from app.core.config import settings
from app.models import Payment, PaymentWebhookEvent
from app.services import razorpay

KEY_SECRET = "test_key_secret_value"
WEBHOOK_SECRET = "test_webhook_secret_value"


class FakeRazorpay:
    """Stands in for the Razorpay API and records what was asked of it."""

    def __init__(self):
        self.orders = []
        self.payments = {}
        self.refunds = []
        self.captures = []
        self.refund_status = "processed"
        self.fail_with = None

    def _maybe_fail(self):
        if self.fail_with:
            raise razorpay.RazorpayError(self.fail_with)

    def create_order(self, amount_paise, receipt, notes):
        self._maybe_fail()
        order = {"id": f"order_test{len(self.orders) + 1}", "amount": amount_paise}
        self.orders.append(order | {"receipt": receipt, "notes": notes})
        return order

    def fetch_payment(self, payment_id):
        self._maybe_fail()
        return self.payments[payment_id]

    def capture_payment(self, payment_id, amount_paise):
        self._maybe_fail()
        self.captures.append(payment_id)
        self.payments[payment_id]["status"] = "captured"
        return self.payments[payment_id]

    def refund_payment(self, payment_id, amount_paise, receipt):
        self._maybe_fail()
        self.refunds.append((payment_id, amount_paise))
        return {"id": f"rfnd_test{len(self.refunds)}", "status": self.refund_status}

    def add_payment(self, payment_id, order_id, amount, status="captured", **extra):
        self.payments[payment_id] = {
            "id": payment_id,
            "order_id": order_id,
            "amount": amount,
            "currency": "INR",
            "status": status,
        } | extra


@pytest.fixture
def gateway(monkeypatch):
    fake = FakeRazorpay()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", KEY_SECRET)
    monkeypatch.setattr(settings, "razorpay_webhook_secret", WEBHOOK_SECRET)
    for name in ("create_order", "fetch_payment", "capture_payment", "refund_payment"):
        monkeypatch.setattr(razorpay, name, getattr(fake, name))
    return fake


@pytest.fixture
def online_order(client, make_customer, make_product, make_address, add_to_cart, auth):
    customer = make_customer()
    product = make_product(retail_price="249.50", stock_quantity=10)
    add_to_cart(customer, product, 2)
    order = client.post(
        "/api/orders/",
        json={"address_id": make_address(customer), "payment_method": "online"},
        headers=auth(customer),
    ).json()
    return {"customer": customer, "order": order, "product": product}


def start_payment(client, auth, online_order):
    return client.post(
        "/api/payments/razorpay/order",
        json={"order_id": online_order["order"]["id"]},
        headers=auth(online_order["customer"]),
    )


def checkout_signature(order_id, payment_id, secret=KEY_SECRET):
    message = f"{order_id}|{payment_id}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify(client, auth, customer, order_id, payment_id, signature=None):
    return client.post(
        "/api/payments/razorpay/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature or checkout_signature(order_id, payment_id),
        },
        headers=auth(customer),
    )


def send_webhook(client, event, event_id="evt_1", secret=WEBHOOK_SECRET):
    body = json.dumps(event).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/payments/razorpay/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": event_id,
        },
    )


def payment_event(event, payment_id, order_id, amount, status="captured"):
    entity = {
        "id": payment_id,
        "order_id": order_id,
        "amount": amount,
        "currency": "INR",
        "status": status,
    }
    return {"event": event, "payload": {"payment": {"entity": entity}}}


def order_payment_status(client, auth, online_order):
    order = client.get(
        f"/api/orders/{online_order['order']['id']}",
        headers=auth(online_order["customer"]),
    ).json()
    return order["payment_status"]


def stock_of(db, product):
    db.expire_all()
    return product.stock_quantity


class TestConfig:
    def test_online_payment_is_off_without_keys(self, client, monkeypatch):
        monkeypatch.setattr(settings, "razorpay_key_id", None)
        monkeypatch.setattr(settings, "razorpay_key_secret", None)

        response = client.get("/api/payments/config")

        assert response.json() == {"online_enabled": False, "key_id": None}

    def test_config_shows_only_the_public_key(self, client, gateway):
        response = client.get("/api/payments/config")

        assert response.json() == {"online_enabled": True, "key_id": "rzp_test_key"}
        assert KEY_SECRET not in response.text

    def test_starting_payment_without_keys_is_refused(
        self, client, auth, online_order, monkeypatch
    ):
        monkeypatch.setattr(settings, "razorpay_key_id", None)

        assert start_payment(client, auth, online_order).status_code == 503


class TestStartingPayment:
    def test_creates_a_razorpay_order_for_the_exact_amount(
        self, client, auth, online_order, gateway
    ):
        response = start_payment(client, auth, online_order)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["amount"] == 54900  # 2 x 249.50 + Rs 50 delivery, in paise
        assert body["currency"] == "INR"
        assert body["key_id"] == "rzp_test_key"
        assert body["razorpay_order_id"] == "order_test1"
        assert gateway.orders[0]["notes"] == {
            "order_id": str(online_order["order"]["id"])
        }

    def test_retrying_reuses_the_same_razorpay_order(
        self, client, auth, online_order, gateway
    ):
        first = start_payment(client, auth, online_order).json()
        second = start_payment(client, auth, online_order).json()

        assert first["razorpay_order_id"] == second["razorpay_order_id"]
        assert len(gateway.orders) == 1

    def test_another_customer_cannot_pay_for_the_order(
        self, client, auth, make_customer, online_order, gateway
    ):
        response = client.post(
            "/api/payments/razorpay/order",
            json={"order_id": online_order["order"]["id"]},
            headers=auth(make_customer()),
        )

        assert response.status_code == 404

    def test_cash_on_delivery_order_cannot_start_online_payment(
        self,
        client,
        auth,
        make_customer,
        make_product,
        make_address,
        add_to_cart,
        gateway,
    ):
        customer = make_customer()
        add_to_cart(customer, make_product(), 1)
        order = client.post(
            "/api/orders/",
            json={"address_id": make_address(customer)},
            headers=auth(customer),
        ).json()

        response = client.post(
            "/api/payments/razorpay/order",
            json={"order_id": order["id"]},
            headers=auth(customer),
        )

        assert response.status_code == 400

    def test_gateway_failure_returns_502_and_saves_nothing(
        self, client, db, auth, online_order, gateway
    ):
        gateway.fail_with = "down"

        assert start_payment(client, auth, online_order).status_code == 502
        assert db.query(Payment).count() == 0


class TestVerifyingCheckout:
    def test_valid_captured_payment_marks_the_order_paid(
        self, client, db, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()
        gateway.add_payment("pay_1", rzp_order["razorpay_order_id"], 54900)

        response = verify(
            client,
            auth,
            online_order["customer"],
            rzp_order["razorpay_order_id"],
            "pay_1",
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "paid"
        assert response.json()["transaction_reference"] == "pay_1"
        assert order_payment_status(client, auth, online_order) == "paid"

    def test_authorized_payment_is_captured_first(
        self, client, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()
        gateway.add_payment(
            "pay_1", rzp_order["razorpay_order_id"], 54900, status="authorized"
        )

        response = verify(
            client,
            auth,
            online_order["customer"],
            rzp_order["razorpay_order_id"],
            "pay_1",
        )

        assert response.json()["status"] == "paid"
        assert gateway.captures == ["pay_1"]

    def test_wrong_signature_is_rejected(self, client, auth, online_order, gateway):
        rzp_order = start_payment(client, auth, online_order).json()
        gateway.add_payment("pay_1", rzp_order["razorpay_order_id"], 54900)

        response = verify(
            client,
            auth,
            online_order["customer"],
            rzp_order["razorpay_order_id"],
            "pay_1",
            signature=checkout_signature(
                rzp_order["razorpay_order_id"], "pay_1", "wrong"
            ),
        )

        assert response.status_code == 400
        assert order_payment_status(client, auth, online_order) == "pending"

    def test_payment_for_a_smaller_amount_is_rejected(
        self, client, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()
        gateway.add_payment("pay_1", rzp_order["razorpay_order_id"], 100)

        response = verify(
            client,
            auth,
            online_order["customer"],
            rzp_order["razorpay_order_id"],
            "pay_1",
        )

        assert response.status_code == 400
        assert order_payment_status(client, auth, online_order) == "pending"

    def test_payment_from_another_razorpay_order_is_rejected(
        self, client, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()
        gateway.add_payment("pay_1", "order_someone_else", 54900)

        response = verify(
            client,
            auth,
            online_order["customer"],
            rzp_order["razorpay_order_id"],
            "pay_1",
        )

        assert response.status_code == 400

    def test_verifying_twice_changes_nothing(
        self, client, db, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()
        gateway.add_payment("pay_1", rzp_order["razorpay_order_id"], 54900)
        args = (client, auth, online_order["customer"], rzp_order["razorpay_order_id"])

        verify(*args, "pay_1")
        second = verify(*args, "pay_1")

        assert second.status_code == 200
        assert db.query(Payment).filter_by(status="paid").count() == 1

    def test_failed_payment_marks_the_attempt_failed_and_allows_retry(
        self, client, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()
        gateway.add_payment(
            "pay_1",
            rzp_order["razorpay_order_id"],
            54900,
            status="failed",
            error_description="Card declined",
        )

        response = verify(
            client,
            auth,
            online_order["customer"],
            rzp_order["razorpay_order_id"],
            "pay_1",
        )

        assert response.json()["status"] == "failed"
        assert order_payment_status(client, auth, online_order) == "failed"
        retry = start_payment(client, auth, online_order)
        assert retry.status_code == 200
        assert retry.json()["razorpay_order_id"] == "order_test2"
        assert order_payment_status(client, auth, online_order) == "pending"


class TestWebhook:
    def test_bad_signature_is_rejected(self, client, gateway):
        response = send_webhook(client, {"event": "payment.captured"}, secret="wrong")

        assert response.status_code == 400

    def test_payment_captured_marks_the_order_paid(
        self, client, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()

        response = send_webhook(
            client,
            payment_event(
                "payment.captured", "pay_1", rzp_order["razorpay_order_id"], 54900
            ),
        )

        assert response.json() == {"status": "ok"}
        assert order_payment_status(client, auth, online_order) == "paid"

    def test_a_repeated_event_is_applied_once(
        self, client, db, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()
        event = payment_event(
            "payment.captured", "pay_1", rzp_order["razorpay_order_id"], 54900
        )

        send_webhook(client, event, event_id="evt_same")
        again = send_webhook(client, event, event_id="evt_same")

        assert again.json() == {"status": "duplicate"}
        assert db.query(PaymentWebhookEvent).count() == 1

    def test_wrong_amount_is_ignored(self, client, auth, online_order, gateway):
        rzp_order = start_payment(client, auth, online_order).json()

        response = send_webhook(
            client,
            payment_event(
                "payment.captured", "pay_1", rzp_order["razorpay_order_id"], 1
            ),
        )

        assert response.json() == {"status": "ignored"}
        assert order_payment_status(client, auth, online_order) == "pending"

    def test_payment_failed_marks_the_order_failed(
        self, client, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()

        send_webhook(
            client,
            payment_event(
                "payment.failed",
                "pay_1",
                rzp_order["razorpay_order_id"],
                54900,
                status="failed",
            ),
        )

        assert order_payment_status(client, auth, online_order) == "failed"

    def test_late_failure_does_not_undo_a_payment(
        self, client, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()
        rzp_id = rzp_order["razorpay_order_id"]

        send_webhook(client, payment_event("payment.captured", "pay_1", rzp_id, 54900))
        send_webhook(
            client,
            payment_event("payment.failed", "pay_1", rzp_id, 54900, status="failed"),
            event_id="evt_2",
        )

        assert order_payment_status(client, auth, online_order) == "paid"

    def test_unknown_order_is_accepted_and_ignored(self, client, gateway):
        response = send_webhook(
            client, payment_event("payment.captured", "pay_x", "order_unknown", 100)
        )

        assert response.status_code == 200


def pay(client, auth, online_order, gateway):
    rzp_order = start_payment(client, auth, online_order).json()
    gateway.add_payment("pay_1", rzp_order["razorpay_order_id"], 54900)
    verify(
        client, auth, online_order["customer"], rzp_order["razorpay_order_id"], "pay_1"
    )
    return rzp_order


class TestRefunds:
    def test_customer_cancelling_a_paid_order_gets_a_full_refund(
        self, client, db, auth, online_order, gateway
    ):
        pay(client, auth, online_order, gateway)

        response = client.post(
            f"/api/orders/{online_order['order']['id']}/cancel",
            headers=auth(online_order["customer"]),
        )

        assert response.status_code == 200, response.text
        assert response.json()["payment_status"] == "refunded"
        assert gateway.refunds == [("pay_1", 54900)]
        assert stock_of(db, online_order["product"]) == 10

    def test_admin_cancelling_a_paid_order_refunds_it(
        self, client, auth, make_customer, online_order, gateway
    ):
        pay(client, auth, online_order, gateway)
        admin = make_customer(role="admin")

        response = client.patch(
            f"/api/admin/orders/{online_order['order']['id']}/status",
            json={"status": "cancelled"},
            headers=auth(admin),
        )

        assert response.status_code == 200, response.text
        assert response.json()["payment_status"] == "refunded"

    def test_refund_still_processing_is_completed_by_the_webhook(
        self, client, auth, online_order, gateway
    ):
        pay(client, auth, online_order, gateway)
        gateway.refund_status = "pending"

        cancelled = client.post(
            f"/api/orders/{online_order['order']['id']}/cancel",
            headers=auth(online_order["customer"]),
        ).json()
        assert cancelled["payment_status"] == "refund_pending"

        send_webhook(
            client,
            {
                "event": "refund.processed",
                "payload": {
                    "refund": {"entity": {"id": "rfnd_test1", "payment_id": "pay_1"}}
                },
            },
            event_id="evt_refund",
        )

        assert order_payment_status(client, auth, online_order) == "refunded"

    def test_refund_failure_keeps_the_order_and_the_stock(
        self, client, db, auth, online_order, gateway
    ):
        pay(client, auth, online_order, gateway)
        gateway.fail_with = "refund refused"

        response = client.post(
            f"/api/orders/{online_order['order']['id']}/cancel",
            headers=auth(online_order["customer"]),
        )

        assert response.status_code == 502
        assert order_payment_status(client, auth, online_order) == "paid"
        assert stock_of(db, online_order["product"]) == 8

    def test_cancelling_an_unpaid_online_order_needs_no_refund(
        self, client, auth, online_order, gateway
    ):
        start_payment(client, auth, online_order)

        response = client.post(
            f"/api/orders/{online_order['order']['id']}/cancel",
            headers=auth(online_order["customer"]),
        )

        assert response.status_code == 200
        assert gateway.refunds == []

    def test_payment_arriving_after_cancellation_is_refunded(
        self, client, auth, online_order, gateway
    ):
        rzp_order = start_payment(client, auth, online_order).json()
        client.post(
            f"/api/orders/{online_order['order']['id']}/cancel",
            headers=auth(online_order["customer"]),
        )

        send_webhook(
            client,
            payment_event(
                "payment.captured", "pay_late", rzp_order["razorpay_order_id"], 54900
            ),
        )

        assert gateway.refunds == [("pay_late", 54900)]
        assert order_payment_status(client, auth, online_order) == "refunded"


def test_paise_conversion():
    assert razorpay.to_paise(Decimal("4692.87")) == 469287
    assert razorpay.to_paise(Decimal("0.10")) == 10
