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