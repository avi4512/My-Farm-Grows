from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import app.models
from app.api.routes import admin
from app.api.routes.address import router as addresses_router
from app.api.routes.auth import router as auth_router
from app.api.routes.cart import router as cart_router
from app.api.routes.order import router as orders_router
from app.api.routes.payment import router as payments_router
from app.api.routes.products import router as products_router

# The database schema is managed exclusively by Alembic:
#     alembic upgrade head
# The application must not create or alter tables on startup.

app = FastAPI(
    title="My Farm Grows API",
    description="Online grocery ordering platform for retail and wholesale customers",
    version="0.1.0",
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"

app.mount(
    "/static",
    StaticFiles(directory=str(FRONTEND_DIR)),
    name="static",
)

app.include_router(products_router)
app.include_router(auth_router)
app.include_router(admin.router)
app.include_router(addresses_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(payments_router)


@app.get("/", include_in_schema=False)
def home():
    """Serve the storefront; the API lives under /api."""
    return FileResponse(FRONTEND_INDEX)


@app.get("/health")
def health_check():
    return {"status": "healthy"}
