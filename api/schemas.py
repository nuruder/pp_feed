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


# --- Product Types ---

class ProductTypeSchema(BaseModel):
    id: int
    name: str
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
    size_cm: float | None = None

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
    product_type: str | None = None
    categories: list[str] = []
    stock_quantity: int = 0
    in_stock: bool = False
    price_regular: float | None = None
    price_original: float | None = None
    price_special: float | None = None
    price_wholesale: float | None = None
    price_without_tax: float | None = None

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
    product_type: ProductTypeSchema | None = None
    stock_quantity: int = 0
    in_stock: bool = False
    categories: list[CategoryShort] = []
    sizes: list[SizeSchema] = []
    latest_price: PriceSnapshotSchema | None = None
    price_history: list[PriceSnapshotSchema] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Paginated responses ---

class PaginatedProducts(BaseModel):
    items: list[ProductShort]
    total: int
    page: int
    page_size: int
    pages: int


class PaginatedBrands(BaseModel):
    items: list[BrandSchema]
    total: int
    page: int
    page_size: int
    pages: int


class PaginatedProductTypes(BaseModel):
    items: list[ProductTypeSchema]
    total: int
    page: int
    page_size: int
    pages: int


class PaginatedPrices(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
    pages: int


# --- Web App schemas ---

class WebAppCategory(BaseModel):
    id: int
    name: str
    products_count: int = 0

    model_config = {"from_attributes": True}


class WebAppProductShort(BaseModel):
    id: int
    name: str
    image_url: str | None = None
    price: float          # customer price = (wholesale + regular) / 2
    price_old: float      # strikethrough = price_regular
    in_stock: bool = False

    model_config = {"from_attributes": True}


class WebAppProductDetail(BaseModel):
    id: int
    name: str
    image_url: str | None = None
    images: list[str] = []
    description: str | None = None
    price: float
    price_old: float
    in_stock: bool = False
    stock_quantity: int = 0
    sizes: list[SizeSchema] = []

    model_config = {"from_attributes": True}


class OrderItemCreate(BaseModel):
    product_id: int
    size_label: str | None = None
    quantity: int = 1


class OrderCreate(BaseModel):
    user_id: int
    user_first_name: str | None = None
    user_last_name: str | None = None
    username: str | None = None
    customer_name: str
    customer_phone: str
    items: list[OrderItemCreate]


class OrderItemSchema(BaseModel):
    product_id: int
    product_name: str
    size_label: str | None = None
    quantity: int
    price: float

    model_config = {"from_attributes": True}


class OrderSchema(BaseModel):
    id: int
    status: str
    customer_name: str
    customer_phone: str
    total: float
    items: list[OrderItemSchema]
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Stats ---

class StatsSchema(BaseModel):
    total_products: int
    total_categories: int
    total_brands: int
    total_product_types: int = 0
    in_stock_products: int
    last_scrape: datetime | None = None
