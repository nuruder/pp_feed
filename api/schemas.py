from datetime import datetime
from pydantic import BaseModel


# --- Categories ---

class CategoryShort(BaseModel):
    id: int
    name: str
    url: str
    level: int
    parent_id: int | None
    children_count: int = 0
    products_count: int = 0

    model_config = {"from_attributes": True}


class CategoryTree(BaseModel):
    id: int
    name: str
    url: str
    level: int
    children: list["CategoryTree"] = []
    products_count: int = 0

    model_config = {"from_attributes": True}


# --- Brands ---

class BrandSchema(BaseModel):
    id: int
    name: str
    products_count: int = 0

    model_config = {"from_attributes": True}


# --- Sizes ---

class SizeSchema(BaseModel):
    size_label: str
    in_stock: bool
    quantity: int = 0

    model_config = {"from_attributes": True}


# --- Prices ---

class PriceSnapshotSchema(BaseModel):
    timestamp: datetime
    price_regular: float | None = None
    price_original: float | None = None
    price_special: float | None = None
    price_wholesale: float | None = None
    price_without_tax: float | None = None
    stock_quantity: int = 0
    in_stock: bool = False

    model_config = {"from_attributes": True}


# --- Products ---

class ProductShort(BaseModel):
    id: int
    external_id: str
    name: str
    url: str
    image_url: str | None = None
    brand: str | None = None
    categories: list[str] = []
    in_stock: bool = False
    price_regular: float | None = None
    price_original: float | None = None
    price_wholesale: float | None = None

    model_config = {"from_attributes": True}


class ProductDetail(BaseModel):
    id: int
    external_id: str
    name: str
    url: str
    image_url: str | None = None
    description: str | None = None
    model: str | None = None
    brand: BrandSchema | None = None
    categories: list[CategoryShort] = []
    sizes: list[SizeSchema] = []
    latest_price: PriceSnapshotSchema | None = None
    price_history: list[PriceSnapshotSchema] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Paginated response ---

class PaginatedProducts(BaseModel):
    items: list[ProductShort]
    total: int
    page: int
    page_size: int
    pages: int


# --- Stats ---

class StatsSchema(BaseModel):
    total_products: int
    total_categories: int
    total_brands: int
    in_stock_products: int
    last_scrape: datetime | None = None
