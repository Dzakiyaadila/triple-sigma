from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    store_id: str
    store_name: str
    city: Optional[str] = None


class DatasetProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku_id: str
    product_name: str
    category: Optional[str] = None


class DatasetReadiness(BaseModel):
    dataset_id: str
    source_type: str
    days_covered: int
    store_count: int
    sku_count: int
    supplier_count: int
    transaction_count: int
    min_date: date | None = None
    max_date: date | None = None
    calendar_min_date: date | None = None
    calendar_max_date: date | None = None
    is_ready: bool
    warnings: list[str] = Field(default_factory=list)


class UploadIssue(BaseModel):
    where: str
    message: str
    severity: Literal["warning", "error"]


class DatasetUploadResponse(BaseModel):
    dataset_id: str
    source_type: str = "upload"
    data_hash: str | None = None
    days_covered: int
    store_count: int
    sku_count: int
    supplier_count: int = 0
    transaction_count: int
    min_date: date | None = None
    max_date: date | None = None
    calendar_min_date: date | None = None
    calendar_max_date: date | None = None
    is_ready: bool
    issues: list[UploadIssue] = Field(default_factory=list)
