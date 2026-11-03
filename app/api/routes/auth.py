from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import secrets

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, get_current_customer
from app.db.session import get_db
from app.models.customer import Customer
from app.models.email_otp import EmailOTP
from app.schemas.customer import CustomerResponse, TokenResponse
from app.services.auth import hash_password, verify_password
from app.services.email import otp_email_html, send_email

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
OTP_TTL_MINUTES = 5
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


class RegistrationOTPRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    customer_type: str = "retail"


class EmailOTPRequest(BaseModel):
    email: EmailStr


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\\d{6}$")


class RegistrationCompleteRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr
    reset_token: str
    new_password: str = Field(min_length=8, max_length=128)


class GoogleAuthRequest(BaseModel):
    credential: str = Field(min_length=20)


def _normal_email(value: str) -> str:
    return value.strip().lower()


def _otp_hash(email: str, purpose: str, otp: str) -> str:
    message = f"{email}:{purpose}:{otp}".encode()
    return hmac.new(settings.jwt_secret_key.encode(), message, hashlib.sha256).hexdigest()


def _latest_otp(db: Session, email: str, purpose: str) -> EmailOTP | None:
    return db.scalar(
        select(EmailOTP).where(
            EmailOTP.email == email,
            EmailOTP.purpose == purpose,
        ).order_by(EmailOTP.id.desc()).limit(1)
    )


async def _issue_otp(db: Session, email: str, purpose: str, name: str | None = None, customer_type: str | None = None) -> None:
    now = datetime.now(UTC)
    previous = _latest_otp(db, email, purpose)
    recent_count = len(
        db.scalars(
            select(EmailOTP.id).where(
                EmailOTP.email == email,
                EmailOTP.purpose == purpose,
                EmailOTP.created_at >= now - timedelta(hours=24),
            )
        ).all()
    )
    if recent_count >= 10:
        raise HTTPException(status_code=429, detail="Too many verification emails requested. Try again tomorrow.")
    if previous and previous.last_sent_at > now - timedelta(seconds=OTP_RESEND_SECONDS):
        wait = OTP_RESEND_SECONDS - int((now - previous.last_sent_at).total_seconds())
        raise HTTPException(status_code=429, detail=f"Please wait {max(wait, 1)} seconds before requesting another code.")
    otp = f"{secrets.randbelow(1_000_000):06d}"
    record = EmailOTP(
        email=email,
        purpose=purpose,
        code_hash=_otp_hash(email, purpose, otp),
        pending_name=name,
        customer_type=customer_type,
        attempts=0,
        expires_at=now + timedelta(minutes=OTP_TTL_MINUTES),
        last_sent_at=now,
        verified_at=None,
    )
    db.add(record)
    db.commit()
    try:
        await send_email(email, "Your My Farm Grows verification code", otp_email_html(otp, purpose))
    except Exception as exc:
        db.delete(record)
        db.commit()
        raise HTTPException(status_code=503, detail="Unable to send verification email. Please try again later.") from exc


def _check_otp(db: Session, email: str, purpose: str, otp: str) -> EmailOTP:
    record = _latest_otp(db, email, purpose)
    now = datetime.now(UTC)
    if record is None or record.expires_at < now:
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired. Request a new code.")
    expected = _otp_hash(email, purpose, otp)
    if not hmac.compare_digest(record.code_hash, expected):
        if record.verified_at is None:
            record.attempts += 1
            db.commit()
            if record.attempts >= OTP_MAX_ATTEMPTS:
                raise HTTPException(status_code=429, detail="Too many incorrect attempts. Request a new code.")
        raise HTTPException(status_code=400, detail="Incorrect verification code.")
    if record.verified_at is not None:
        return record
    if record.attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many incorrect attempts. Request a new code.")
    record.verified_at = now
    db.commit()
    return record


@router.post("/register/request-otp")
async def request_registration_otp(payload: RegistrationOTPRequest, db: Session = Depends(get_db)):
    email = _normal_email(str(payload.email))
    if payload.customer_type not in {"retail", "wholesale"}:
        raise HTTPException(status_code=422, detail="Invalid customer type.")
    if db.scalar(select(Customer.id).where(Customer.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    await _issue_otp(db, email, "registration", payload.name.strip(), payload.customer_type)
    return {"message": "Verification code sent.", "expires_in_seconds": 300, "resend_after_seconds": OTP_RESEND_SECONDS}


@router.post("/register/verify-otp")
def verify_registration_otp(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    email = _normal_email(str(payload.email))
    record = _check_otp(db, email, "registration", payload.otp)
    return {"verified": True, "message": "Email verified. You can now create your password."}


@router.post("/register/complete", response_model=TokenResponse, status_code=201)
def complete_registration(payload: RegistrationCompleteRequest, db: Session = Depends(get_db)):
    email = _normal_email(str(payload.email))
    record = _latest_otp(db, email, "registration")
    if not record or not record.verified_at or record.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Verify your email before creating an account.")
    if db.scalar(select(Customer.id).where(Customer.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    customer = Customer(
        name=record.pending_name or email.split("@")[0],
        email=email,
        hashed_password=hash_password(payload.password),
        customer_type=record.customer_type or "retail",
        role="customer",
        is_active=True,
        email_verified=True,
    )
    db.add(customer)
    db.delete(record)
    try:
        db.commit()
        db.refresh(customer)
    except Exception:
        db.rollback()
        raise
    return TokenResponse(access_token=create_access_token(customer.id))


@router.post("/login", response_model=TokenResponse)
def login_customer(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = _normal_email(form_data.username)
    customer = db.scalar(select(Customer).where(Customer.email == email))
    if customer is None or not verify_password(form_data.password, customer.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    if not customer.is_active:
        raise HTTPException(status_code=403, detail="This account is inactive")
    if not customer.email_verified:
        raise HTTPException(status_code=403, detail="Please verify your email address before logging in.")
    return TokenResponse(access_token=create_access_token(customer.id))


@router.post("/google", response_model=TokenResponse)
def google_sign_in(payload: GoogleAuthRequest, db: Session = Depends(get_db)):
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    try:
        claims = google_id_token.verify_oauth2_token(payload.credential, google_requests.Request(), settings.google_client_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Google credential.") from exc
    email = _normal_email(claims.get("email", ""))
    google_sub = claims.get("sub")
    if not email or not google_sub or claims.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Google account email is not verified.")
    customer = db.scalar(select(Customer).where(Customer.email == email))
    if customer:
        if customer.google_sub and customer.google_sub != google_sub:
            raise HTTPException(status_code=409, detail="This email is linked to another Google account.")
        customer.google_sub = google_sub
        customer.email_verified = True
    else:
        customer = Customer(
            name=(claims.get("name") or email.split("@")[0])[:100],
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(48)),
            customer_type="retail",
            role="customer",
            is_active=True,
            email_verified=True,
            google_sub=google_sub,
        )
        db.add(customer)
    try:
        db.commit()
        db.refresh(customer)
    except Exception:
        db.rollback()
        raise
    if not customer.is_active:
        raise HTTPException(status_code=403, detail="This account is inactive.")
    return TokenResponse(access_token=create_access_token(customer.id))


@router.post("/password/forgot/request-otp")
async def forgot_password_request(payload: EmailOTPRequest, db: Session = Depends(get_db)):
    email = _normal_email(str(payload.email))
    customer = db.scalar(select(Customer).where(Customer.email == email))
    # Generic response avoids revealing whether an email is registered.
    if customer:
        await _issue_otp(db, email, "password_reset")
    return {"message": "If an account exists for this email, a verification code has been sent.", "expires_in_seconds": 300, "resend_after_seconds": OTP_RESEND_SECONDS}


@router.post("/password/forgot/verify-otp")
def forgot_password_verify(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    email = _normal_email(str(payload.email))
    record = _check_otp(db, email, "password_reset", payload.otp)
    reset_token = jwt.encode(
        {"sub": email, "purpose": "password_reset", "jti": str(record.id), "exp": datetime.now(UTC) + timedelta(minutes=10)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"verified": True, "reset_token": reset_token}


@router.post("/password/forgot/reset")
async def reset_password(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    try:
        claims = jwt.decode(payload.reset_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Password reset session is invalid or expired.") from exc
    email = _normal_email(str(payload.email))
    if claims.get("purpose") != "password_reset" or claims.get("sub") != email:
        raise HTTPException(status_code=400, detail="Password reset session is invalid.")
    otp_record = db.get(EmailOTP, int(claims.get("jti", "0")))
    if not otp_record or otp_record.email != email or otp_record.purpose != "password_reset" or not otp_record.verified_at:
        raise HTTPException(status_code=400, detail="Password reset session has already been used or is invalid.")
    customer = db.scalar(select(Customer).where(Customer.email == email))
    if not customer:
        raise HTTPException(status_code=404, detail="Account not found.")
    customer.hashed_password = hash_password(payload.new_password)
    db.delete(otp_record)
    db.commit()
    try:
        from app.services.email import send_email
        await send_email(
            email,
            "Your My Farm Grows password was changed",
            "<p>Your My Farm Grows password was changed successfully. If you did not do this, contact support immediately.</p>",
        )
    except Exception:
        # Password change remains successful; notification delivery can be retried operationally.
        pass
    return {"message": "Password updated successfully. Please log in."}


@router.get("/me", response_model=CustomerResponse)
def get_my_profile(current_customer: Customer = Depends(get_current_customer)):
    return current_customer


@router.get("/config")
def authentication_config():
    # Google client ID is public by design; never return provider secrets.
    return {"google_client_id": settings.google_client_id}
