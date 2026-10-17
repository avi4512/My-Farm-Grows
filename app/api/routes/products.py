
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Product
from app.schemas.product import ProductCreate, ProductResponse,ProductUpdate

from typing import Optional
from app.core.permissions import require_admin
from app.models.customer import Customer
from app.services.inventory import record_inventory_movement

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
    current_admin: Customer = Depends(require_admin),
):
    try:
        db_product = Product(**product.model_dump())
        if db_product.stock_quantity < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stock quantity cannot be negative",
            )
        db.add(db_product)
        db.flush()

        if db_product.stock_quantity > 0:
            record_inventory_movement(
                db,
                product=db_product,
                movement_type="initial_stock",
                quantity_change=db_product.stock_quantity,
                previous_stock=0,
                new_stock=db_product.stock_quantity,
                reason="Initial stock when product was created",
                changed_by_customer_id=current_admin.id,
            )

        db.commit()
        db.refresh(db_product)
        return db_product
    except Exception:
        db.rollback()
        raise


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


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .with_for_update()
        .first()
    )

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    update_data = product_data.model_dump(exclude_unset=True)
    if (
        "stock_quantity" in update_data
        and update_data["stock_quantity"] < 0
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stock quantity cannot be negative",
        )

    previous_stock = product.stock_quantity
    old_name = product.name

    try:
        for field, value in update_data.items():
            setattr(product, field, value)

        db.flush()
        new_stock = product.stock_quantity
        stock_delta = new_stock - previous_stock

        if stock_delta != 0:
            record_inventory_movement(
                db,
                product=product,
                movement_type="stock_adjustment",
                quantity_change=stock_delta,
                previous_stock=previous_stock,
                new_stock=new_stock,
                reason=(
                    f"Administrator updated stock for product "
                    f"'{old_name}'"
                ),
                changed_by_customer_id=current_admin.id,
            )

        db.commit()
        db.refresh(product)
        return product
    except Exception:
        db.rollback()
        raise



@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
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

