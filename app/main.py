from pathlib import Path
import logging
import time

from fastapi import FastAPI, Request
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
from app.core.logging_config import configure_logging

# The database schema is managed exclusively by Alembic:
#     alembic upgrade head
# The application must not create or alter tables on startup.

configure_logging()
logger = logging.getLogger("myfarmgrows.http")

app = FastAPI(
    title="My Farm Grow API",
    description="Online grocery ordering platform for retail and wholesale customers",
    version="0.1.0",
)

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.exception(
            "request_failed method=%s path=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise


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
