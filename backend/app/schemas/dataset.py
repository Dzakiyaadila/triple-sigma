from pydantic import BaseModel
from typing import Optional, Literal


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

class UploadIssue(BaseModel):
    where: str
    message: str
    severity: Literal["warning", "error"]


class DatasetUploadResponse(BaseModel):
    dataset_id: str
    source_type: str = "upload"
    days_covered: int
    store_count: int
    sku_count: int
    supplier_count: int = 0
    transaction_count: int
    is_ready: bool
    issues: list[UploadIssue] = []
    
class SkuOption(BaseModel):
    sku_id: str
    product_name: str
    category: str

    class Config:
        from_attributes = True