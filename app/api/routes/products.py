
from alembic.util import status
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Product
from app.schemas.product import ProductCreate, ProductResponse,ProductUpdate

from typing import Optional

router = APIRouter(prefix="/api/products", tags=["Products"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=ProductResponse, status_code=201)
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db),
):
    db_product = Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.get("/", response_model=list[ProductResponse])
def get_products(
    search: Optional[str] = Query(default=None, min_length=1),
    category: Optional[str] = Query(default=None),
    max_price: Optional[float] = Query(default=None, gt=0),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    query = db.query(Product)

    if search:
        query = query.filter(
            Product.name.ilike(f"%{search.strip()}%")
        )

    if category:
        query = query.filter(
            Product.category.ilike(category.strip())
        )

    if max_price is not None:
        query = query.filter(
            Product.retail_price <= max_price
        )

    if active_only:
        query = query.filter(Product.is_active.is_(True))

    return (
        query.order_by(Product.id)
        .offset(skip)
        .limit(limit)
        .all()
    )



@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.is_active.is_(True),
    ).first()

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return product

@router.put(
    "/{product_id}",
    response_model=ProductResponse,
)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .first()
    )

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    update_data = product_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    return product


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .first()
    )

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    db.delete(product)
    db.commit()

    return None
