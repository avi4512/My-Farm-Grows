
from fastapi import FastAPI

from app.db.session import Base, engine
from app.models import Product
from app.api.routes.products import router as products_router
from app.api.routes.auth import router as auth_router
from app.api.routes import admin



Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="My Farm Grows API",
    description="Online grocery ordering platform for retail and wholesale customers",
    version="0.1.0",
)

app.include_router(products_router)
app.include_router(auth_router)
app.include_router(admin.router)


@app.get("/")
def home():
    return {
        "message": "Welcome to My Farm Grows!",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
