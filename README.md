

## Browser storefront integration

The storefront is served by FastAPI at `http://127.0.0.1:8000/`. The interactive
page uses the existing API endpoints for product browsing, customer registration
and login, cart management, addresses, order placement, order history, and order
cancellation. API documentation remains available at `http://127.0.0.1:8000/docs`.

Run the backend from the project root:

```powershell
uv run uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/`. Products must already exist in the database;
the storefront does not insert demo products automatically. Public registration
creates customer accounts only. Admin product creation and editing remain
available through the authenticated admin API endpoints.

**Payment note:** the current UI can create a pending payment transaction for
online-payment orders, but it does not process real online payments because no
payment gateway integration is configured.
