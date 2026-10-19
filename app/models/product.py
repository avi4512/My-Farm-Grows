from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(30), default="kg", nullable=False)
    retail_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    wholesale_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    min_wholesale_quantity: Mapped[int] = mapped_column(
        Integer, default=25, nullable=False
    )
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
