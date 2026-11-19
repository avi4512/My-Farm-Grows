"""Small Razorpay client: orders, payments, refunds and signature checks.

Only the calls this shop needs. Keys come from settings (environment
variables); the key secret and webhook secret never leave the server.
API reference: https://razorpay.com/docs/api/
"""

import hashlib
import hmac
from decimal import ROUND_HALF_UP, Decimal

import httpx

from app.core.config import settings

API_BASE = "https://api.razorpay.com/v1"
TIMEOUT_SECONDS = 15


class RazorpayError(Exception):
    """Razorpay is not configured, unreachable, or rejected the request."""


def to_paise(amount: Decimal) -> int:
    """Rupees to the integer paise Razorpay expects."""
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), ROUND_HALF_UP))


def _client() -> httpx.Client:
    if not settings.online_payments_enabled:
        raise RazorpayError("Online payment is not configured")
    return httpx.Client(
        base_url=API_BASE,
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
        timeout=TIMEOUT_SECONDS,
    )


def _request(method: str, path: str, json: dict | None = None) -> dict:
    try:
        with _client() as client:
            response = client.request(method, path, json=json)
    except httpx.HTTPError as error:
        raise RazorpayError("Could not reach Razorpay") from error
    if response.status_code >= 400:
        try:
            detail = response.json()["error"]["description"]
        except ValueError, KeyError, TypeError:
            detail = f"HTTP {response.status_code}"
        raise RazorpayError(f"Razorpay error: {detail}")
    return response.json()


def create_order(amount_paise: int, receipt: str, notes: dict) -> dict:
    return _request(
        "POST",
        "/orders",
        {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": notes,
        },
    )


def fetch_payment(payment_id: str) -> dict:
    return _request("GET", f"/payments/{payment_id}")


def capture_payment(payment_id: str, amount_paise: int) -> dict:
    return _request(
        "POST",
        f"/payments/{payment_id}/capture",
        {"amount": amount_paise, "currency": "INR"},
    )


def refund_payment(payment_id: str, amount_paise: int, receipt: str) -> dict:
    return _request(
        "POST",
        f"/payments/{payment_id}/refund",
        {"amount": amount_paise, "receipt": receipt},
    )


def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def payment_signature_is_valid(order_id: str, payment_id: str, signature: str) -> bool:
    """Checkout handler signature: HMAC-SHA256 of "order_id|payment_id"."""
    if not settings.razorpay_key_secret or not signature:
        return False
    expected = _hmac_hex(
        settings.razorpay_key_secret, f"{order_id}|{payment_id}".encode()
    )
    return hmac.compare_digest(expected, signature)


def webhook_signature_is_valid(body: bytes, signature: str | None) -> bool:
    """X-Razorpay-Signature: HMAC-SHA256 of the raw body with the webhook secret."""
    if not settings.razorpay_webhook_secret or not signature:
        return False
    expected = _hmac_hex(settings.razorpay_webhook_secret, body)
    return hmac.compare_digest(expected, signature)
