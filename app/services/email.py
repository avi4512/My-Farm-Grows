import httpx

from app.core.config import settings


async def send_email(to_email: str, subject: str, html: str) -> None:
    if not settings.resend_api_key or not settings.email_from:
        raise RuntimeError("Email delivery is not configured. Set RESEND_API_KEY and EMAIL_FROM.")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json"},
            json={"from": settings.email_from, "to": [to_email], "subject": subject, "html": html},
        )
    if response.is_error:
        raise RuntimeError("Email provider rejected the message.")


def otp_email_html(code: str, purpose: str) -> str:
    label = "verify your email address" if purpose == "registration" else "reset your password"
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#26352b">
      <h2>My Farm Grow</h2>
      <p>Use this one-time password to {label}:</p>
      <div style="font-size:32px;font-weight:700;letter-spacing:8px;padding:16px;background:#f2f8f4;border-radius:8px">{code}</div>
      <p>This code expires in 5 minutes. If you did not request it, you can ignore this email.</p>
    </div>
    """
