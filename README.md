# My Farm Grows

Online grocery ordering platform for retail and wholesale customers
(FastAPI, SQLAlchemy, PostgreSQL, Alembic).

## Setup

1. Install dependencies:

   ```powershell
   uv sync
   ```

2. Create your environment file and fill in real values. The app refuses
   to start without `DATABASE_URL` and a `JWT_SECRET_KEY` of at least
   32 characters. Never commit `.env`.

   ```powershell
   copy .env.example .env
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. Create or update the database schema. The schema is managed only by
   Alembic; the application does not create tables on startup.

   ```powershell
   uv run alembic upgrade head
   ```

   The migrations are safe to run on a database that already contains the
   tables (for example one created by an older version of this project).

4. Create an administrator. Register a normal account from the storefront,
   then promote it in PostgreSQL:

   ```sql
   UPDATE customers SET role = 'admin' WHERE email = 'you@example.com';
   ```

5. Run the backend from the project root:

   ```powershell
   uv run uvicorn app.main:app --reload
   ```

## Browser storefront integration

The storefront is served by FastAPI at `http://127.0.0.1:8000/`. The interactive
page uses the existing API endpoints for product browsing, customer registration
and login, cart management, addresses, order placement, order history, order
tracking, payment history and order cancellation. API documentation remains
available at `http://127.0.0.1:8000/docs`.

Products must already exist in the database; the storefront does not insert demo
products automatically. Public registration creates customer accounts only.
Admin product creation and editing remain available through the authenticated
admin API endpoints.

## Delivery and order status

Updating a delivery's progress also moves the order status forward
(packed -> processing, shipped / out for delivery -> shipped,
delivered -> delivered). The order status never moves backwards and
cancelled orders are not changed.

**Payment note:** the current UI can create a pending payment transaction for
online-payment orders, but it does not process real online payments because no
payment gateway integration is configured.

## Finalization updates in this package

### Product-card quantity controls
Product cards now show an Add button until the product is in the authenticated customer's cart. Once added, the card shows minus / quantity / plus controls. These controls update the same cart API used by the cart page. The backend rejects cart quantities above the currently available stock.

### Use my current location
The checkout address form includes a browser geolocation action. It requests permission, obtains coordinates, and uses OpenStreetMap Nominatim reverse geocoding to prefill available locality, city, state, PIN code and country fields. The customer must review the result and manually add apartment/flat and landmark details before saving.

Location lookup requires HTTPS (except localhost), browser location permission, and internet access. The public Nominatim service has usage limits and is suitable for development / low-volume testing, not guaranteed production-scale use. For production, use a provider with an appropriate service agreement or self-hosted geocoding.

### Application request logs
HTTP method, URL path, response status and duration are logged to `logs/app.log`, with rotation (5 MB per file, 5 backups). Request bodies, passwords, cookies, authorization headers and payment data are intentionally not logged. The `logs/` directory is excluded from Git.

### Setup
1. Copy `.env.example` to `.env`.
2. Set a real PostgreSQL `DATABASE_URL`.
3. Generate a unique JWT secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
4. Install dependencies with `uv sync`.
5. Run migrations with `uv run alembic upgrade head`.
6. Start the API with `uv run uvicorn app.main:app --reload`.

### Payment gateway status — action still required
The existing payment endpoints store payment transactions and allow administrative status management. This package does **not** claim that real online payments are integrated. Do not accept real money using the current "online" checkout option. Before production, integrate a payment provider (for example Razorpay) with server-side order creation, signature verification, signed webhook verification, idempotency, amount/currency validation and reconciliation. Merchant credentials must be stored only in environment variables and never committed. Test the full flow in the provider's sandbox before enabling live mode.

### Security and release checklist
- Never commit `.env`; rotate any credentials that have ever been committed or shared.
- Use HTTPS in production.
- Restrict CORS to the actual frontend origin if cross-origin hosting is introduced.
- Configure production database backups and a least-privilege DB user.
- Add rate limiting at the reverse proxy / application layer before public launch.
- Run automated tests and dependency/security scans before deployment.


## Email OTP and Google authentication

### Environment variables

Set these in the private `.env` file (never commit it):

```dotenv
RESEND_API_KEY=re_xxxxxxxxx
EMAIL_FROM=My Farm Grows <verification@your-verified-domain.example>
GOOGLE_CLIENT_ID=your-web-oauth-client-id.apps.googleusercontent.com
```

The Google Identity Services ID-token flow used here requires a **Web application OAuth client ID**. A client secret is not used in this browser ID-token flow and is intentionally not exposed or required. Configure the authorized JavaScript origin for your local development origin and production HTTPS domain in Google Cloud Console.

For Resend, verify the sender domain and configure the exact sender address in `EMAIL_FROM`. The backend calls Resend's API; the API key is never sent to the browser.

### Registration flow

1. `POST /api/auth/register/request-otp` — issue and email a six-digit code.
2. `POST /api/auth/register/verify-otp` — verify the code.
3. `POST /api/auth/register/complete` — create the customer after verification and return the existing JWT token.

OTP codes are HMAC-hashed using the application JWT secret, expire after five minutes, allow at most five incorrect attempts and have a 60-second resend cooldown. The OTP value is never returned by the API.

### Google sign-in

The frontend uses Google Identity Services to obtain an ID token. `POST /api/auth/google` verifies that token on the backend against the configured client ID, checks Google's verified-email claim, and issues the application's existing JWT. New Google users are always assigned the `customer` role. Existing accounts with the same verified email are linked instead of duplicated.

### Password reset

- `POST /api/auth/password/forgot/request-otp`
- `POST /api/auth/password/forgot/verify-otp`
- `POST /api/auth/password/forgot/reset`

The reset token is short-lived and bound to a one-time OTP challenge. The reset endpoint consumes the challenge so the token cannot be reused.

### Existing customer data

The migration backfills `email_verified=true` for all existing customer records, preserving their ability to sign in. New email/password registrations are created only after OTP verification. Google sign-ins are marked verified after backend token validation.

### Migration and dependency update

Run:

```powershell
uv lock
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

`uv.lock` must be regenerated because this feature adds `google-auth` and `httpx`. The build environment used to prepare this archive had no external network access, so the lockfile could not be refreshed here. `uv lock` on your development machine will resolve and write the current lockfile.

### Google / Resend setup validation

- Resend sender domain is verified and `EMAIL_FROM` matches it.
- Google OAuth client type is Web application.
- Authorized JavaScript origins include `http://localhost:8000` for local development and your production HTTPS origin.
- `GOOGLE_CLIENT_ID`, `RESEND_API_KEY` and `EMAIL_FROM` are set only in the backend environment.
- Test registration, resend cooldown, OTP expiry, incorrect-attempt lockout, duplicate email, Google sign-in, password reset and existing administrator login before release.
