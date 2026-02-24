from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean,
    ForeignKey, DateTime, UniqueConstraint, Table,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# Many-to-many association table for products ↔ categories
product_categories = Table(
    "product_categories",
    Base.metadata,
    Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(String(512), nullable=False, unique=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    level = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent")
    products = relationship("Product", secondary=product_categories, back_populates="categories")


class ProductType(Base):
    """Product type/category from the site's datalayer (e.g. 'Padel Rackets', 'Padel Shoes')."""
    __tablename__ = "product_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)

    products = relationship("Product", back_populates="product_type")


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)

    products = relationship("Product", back_populates="brand")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), unique=True, nullable=False)  # site product_id
    name = Column(String(512), nullable=False)
    url = Column(String(512), nullable=False)
    image_url = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True)
    product_type_id = Column(Integer, ForeignKey("product_types.id"), nullable=True)
    model = Column(String(255), nullable=True)
    stock_quantity = Column(Integer, default=0)
    in_stock = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    brand = relationship("Brand", back_populates="products")
    product_type = relationship("ProductType", back_populates="products")
    categories = relationship("Category", secondary=product_categories, back_populates="products")
    sizes = relationship("ProductSize", back_populates="product", cascade="all, delete-orphan")
    price_snapshots = relationship("PriceSnapshot", back_populates="product", cascade="all, delete-orphan")


class ProductSize(Base):
    __tablename__ = "product_sizes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    size_label = Column(String(64), nullable=False)
    in_stock = Column(Boolean, default=False)
    quantity = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = relationship("Product", back_populates="sizes")

    __table_args__ = (
        UniqueConstraint("product_id", "size_label", name="uq_product_size"),
    )


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Guest prices (non-authenticated)
    price_regular = Column(Float, nullable=True)       # current displayed price
    price_original = Column(Float, nullable=True)      # strikethrough / base_price
    price_special = Column(Float, nullable=True)       # special offer price (if any)

    # Wholesale prices (authenticated)
    price_wholesale = Column(Float, nullable=True)

    # Tax info
    price_without_tax = Column(Float, nullable=True)

    # Stock
    stock_quantity = Column(Integer, default=0)
    in_stock = Column(Boolean, default=False)

    product = relationship("Product", back_populates="price_snapshots")
