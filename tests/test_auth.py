import re
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.models import Customer
from app.models.email_otp import EmailOTP

from .conftest import PASSWORD

NEW_PASSWORD = "Brand-New-Pass-7"


def login(client, email, password=PASSWORD):
    return client.post(
        "/api/auth/login", data={"username": email, "password": password}
    )


def code_from(email):
    match = re.search(r">(\d{6})</div>", email["html"])
    assert match, "No verification code in the email"
    return match.group(1)


def wrong_code(code):
    return "000000" if code != "000000" else "111111"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def request_registration(client, email="new@example.com", **extra):
    body = {"name": "New Person", "email": email} | extra
    return client.post("/api/auth/register/request-otp", json=body)


def verify_registration(client, code, email="new@example.com"):
    return client.post(
        "/api/auth/register/verify-otp", json={"email": email, "otp": code}
    )


class TestLogin:
    def test_correct_password_gives_a_working_token(self, client, make_customer):
        customer = make_customer(email="ravi@example.com")

        response = login(client, "ravi@example.com")

        assert response.status_code == 200
        profile = client.get(
            "/api/auth/me", headers=bearer(response.json()["access_token"])
        )
        assert profile.status_code == 200
        assert profile.json()["id"] == customer.id
        assert "hashed_password" not in profile.json()

    def test_email_is_not_case_sensitive(self, client, make_customer):
        make_customer(email="ravi@example.com")

        assert login(client, "  RAVI@Example.com ").status_code == 200

    def test_wrong_password_and_unknown_email_look_the_same(
        self, client, make_customer
    ):
        make_customer(email="ravi@example.com")

        wrong_password = login(client, "ravi@example.com", "not-the-password")
        unknown_email = login(client, "nobody@example.com")

        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json() == unknown_email.json()

    def test_inactive_account_cannot_log_in(self, client, make_customer):
        make_customer(email="ravi@example.com", is_active=False)

        assert login(client, "ravi@example.com").status_code == 403

    def test_unverified_email_cannot_log_in(self, client, make_customer):
        make_customer(email="ravi@example.com", email_verified=False)

        assert login(client, "ravi@example.com").status_code == 403


class TestTokens:
    def test_missing_token_is_rejected(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_garbage_token_is_rejected(self, client):
        assert client.get("/api/auth/me", headers=bearer("garbage")).status_code == 401

    def test_expired_token_is_rejected(self, client, make_customer):
        customer = make_customer()
        token = jwt.encode(
            {"sub": str(customer.id), "exp": datetime.now(UTC) - timedelta(minutes=1)},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401

    def test_token_signed_with_another_key_is_rejected(self, client, make_customer):
        customer = make_customer()
        token = jwt.encode(
            {"sub": str(customer.id), "exp": datetime.now(UTC) + timedelta(minutes=5)},
            "some-other-key-that-is-also-long-enough-for-hs256",
            algorithm=settings.jwt_algorithm,
        )

        assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401

    def test_deactivating_an_account_blocks_its_existing_token(
        self, client, db, make_customer, auth
    ):
        customer = make_customer()
        headers = auth(customer)
        assert client.get("/api/auth/me", headers=headers).status_code == 200

        customer.is_active = False
        db.commit()

        assert client.get("/api/auth/me", headers=headers).status_code == 403

    def test_customer_cannot_use_admin_routes(self, client, make_customer, auth):
        response = client.get("/api/admin/orders", headers=auth(make_customer()))

        assert response.status_code == 403


class TestRegistration:
    def test_full_flow_creates_an_account_that_can_log_in(self, client, db, outbox):
        assert request_registration(client).status_code == 200
        assert outbox[0]["to"] == "new@example.com"

        verified = verify_registration(client, code_from(outbox[0]))
        assert verified.status_code == 200, verified.text

        completed = client.post(
            "/api/auth/register/complete",
            json={"email": "new@example.com", "password": NEW_PASSWORD},
        )
        assert completed.status_code == 201, completed.text

        assert login(client, "new@example.com", NEW_PASSWORD).status_code == 200
        customer = db.query(Customer).filter_by(email="new@example.com").one()
        assert customer.role == "customer"
        assert customer.email_verified is True

    def test_the_code_itself_is_never_stored_or_returned(self, client, db, outbox):
        response = request_registration(client)

        code = code_from(outbox[0])
        assert code not in response.text
        assert db.query(EmailOTP).one().code_hash != code

    def test_cannot_complete_without_verifying(self, client, db):
        request_registration(client)

        response = client.post(
            "/api/auth/register/complete",
            json={"email": "new@example.com", "password": NEW_PASSWORD},
        )

        assert response.status_code == 400
        assert db.query(Customer).count() == 0

    def test_existing_email_is_rejected(self, client, make_customer, outbox):
        make_customer(email="new@example.com")

        assert request_registration(client).status_code == 409
        assert outbox == []

    def test_second_request_within_the_cooldown_is_rejected(self, client, outbox):
        assert request_registration(client).status_code == 200
        assert request_registration(client).status_code == 429
        assert len(outbox) == 1

    def test_invalid_customer_type_is_rejected(self, client):
        response = request_registration(client, customer_type="admin")

        assert response.status_code == 422

    def test_wrong_code_is_rejected(self, client, outbox):
        request_registration(client)

        response = verify_registration(client, wrong_code(code_from(outbox[0])))

        assert response.status_code == 400

    @pytest.mark.parametrize("code", ["12345", "1234567", "abcdef"])
    def test_badly_formed_code_is_rejected(self, client, code):
        request_registration(client)

        assert verify_registration(client, code).status_code == 422

    def test_fifth_wrong_code_locks_out_even_the_right_code(self, client, outbox):
        request_registration(client)
        code = code_from(outbox[0])

        for _ in range(4):
            assert verify_registration(client, wrong_code(code)).status_code == 400

        assert verify_registration(client, wrong_code(code)).status_code == 429
        assert verify_registration(client, code).status_code == 429

    def test_expired_code_is_rejected(self, client, db, outbox):
        request_registration(client)
        db.query(EmailOTP).one().expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

        assert verify_registration(client, code_from(outbox[0])).status_code == 400


class TestPasswordReset:
    def reset_token(self, client, outbox, email):
        client.post("/api/auth/password/forgot/request-otp", json={"email": email})
        response = client.post(
            "/api/auth/password/forgot/verify-otp",
            json={"email": email, "otp": code_from(outbox[-1])},
        )
        assert response.status_code == 200, response.text
        return response.json()["reset_token"]

    def reset(self, client, email, token, password=NEW_PASSWORD):
        return client.post(
            "/api/auth/password/forgot/reset",
            json={"email": email, "reset_token": token, "new_password": password},
        )

    def test_reset_replaces_the_password(self, client, make_customer, outbox):
        make_customer(email="ravi@example.com")
        token = self.reset_token(client, outbox, "ravi@example.com")

        assert self.reset(client, "ravi@example.com", token).status_code == 200

        assert login(client, "ravi@example.com").status_code == 401
        assert login(client, "ravi@example.com", NEW_PASSWORD).status_code == 200

    def test_reset_token_works_only_once(self, client, make_customer, outbox):
        make_customer(email="ravi@example.com")
        token = self.reset_token(client, outbox, "ravi@example.com")
        self.reset(client, "ravi@example.com", token)

        again = self.reset(client, "ravi@example.com", token, "Another-Pass-55")

        assert again.status_code == 400
        assert login(client, "ravi@example.com", "Another-Pass-55").status_code == 401

    def test_reset_token_cannot_change_another_account(
        self, client, make_customer, outbox
    ):
        make_customer(email="ravi@example.com")
        make_customer(email="victim@example.com")
        token = self.reset_token(client, outbox, "ravi@example.com")

        assert self.reset(client, "victim@example.com", token).status_code == 400
        assert login(client, "victim@example.com").status_code == 200

    def test_reset_token_is_not_a_login_token(self, client, make_customer, outbox):
        make_customer(email="ravi@example.com")
        token = self.reset_token(client, outbox, "ravi@example.com")

        assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401

    def test_login_token_cannot_reset_a_password(self, client, make_customer):
        customer = make_customer(email="ravi@example.com")
        token = client.post(
            "/api/auth/login",
            data={"username": customer.email, "password": PASSWORD},
        ).json()["access_token"]

        assert self.reset(client, "ravi@example.com", token).status_code == 400

    def test_unknown_email_gets_the_same_answer_and_no_email(
        self, client, make_customer, outbox
    ):
        make_customer(email="ravi@example.com")
        url = "/api/auth/password/forgot/request-otp"

        known = client.post(url, json={"email": "ravi@example.com"})
        sent_after_known = len(outbox)
        unknown = client.post(url, json={"email": "nobody@example.com"})

        assert known.status_code == unknown.status_code == 200
        assert known.json() == unknown.json()
        assert len(outbox) == sent_after_known == 1
