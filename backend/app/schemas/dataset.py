from pydantic import BaseModel
from typing import Optional


class StoreOut(BaseModel):
    store_id: str
    store_name: str
    city: Optional[str] = None

    class Config:
        from_attributes = True


class DatasetReadiness(BaseModel):
    dataset_id: str
    source_type: str
    days_covered: int
    store_count: int
    sku_count: int
    supplier_count: int
    transaction_count: int
    is_ready: bool
    warnings: list[str] = []