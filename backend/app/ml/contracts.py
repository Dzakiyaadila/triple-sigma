from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PolicyPreset = Literal[
    "lindungi_kas",
    "seimbang",
    "lindungi_ketersediaan",
]


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        protected_namespaces=("model_validate", "model_dump"),
    )


class MLDecisionConstraints(StrictFrozenModel):
    budget_rp: float = Field(gt=0)
    horizon_days: int = Field(default=7, ge=1, le=30)
    policy_preset: PolicyPreset = "seimbang"
    min_fill_rate: float | None = Field(default=None, ge=0, le=1)
    protected_sku_ids: tuple[str, ...] = ()


class ProductSnapshot(StrictFrozenModel):
    sku_id: str
    product_name: str
    category: str
    supplier_id: str
    unit_cost_rp: float = Field(ge=0)
    unit_price_rp: float = Field(ge=0)
    shelf_life_days: float = Field(default=365.0, gt=0)
    is_perishable: bool = False
    lead_time_days_default: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_price(self) -> "ProductSnapshot":
        if self.unit_price_rp < self.unit_cost_rp:
            raise ValueError(
                f"unit_price_rp SKU {self.sku_id} tidak boleh "
                "lebih kecil dari unit_cost_rp"
            )
        return self


class SupplierSnapshot(StrictFrozenModel):
    supplier_id: str
    supplier_name: str
    promised_lead_time_days: float = Field(gt=0)


class SalesHistoryRow(StrictFrozenModel):
    sku_id: str
    sales_date: date
    units_sold: float = Field(ge=0)
    stock_on_hand_start: float = Field(ge=0)
    stock_on_hand_end: float = Field(ge=0)
    stockout_flag: bool
    promo_flag: bool


class InventoryPosition(StrictFrozenModel):
    sku_id: str
    on_hand: float = Field(ge=0)
    as_of_date: date


class OutstandingOrder(StrictFrozenModel):
    order_id: str
    sku_id: str
    supplier_id: str
    order_date: date
    order_qty_units: float = Field(gt=0)
    promised_lead_time_days: float = Field(gt=0)
    expected_arrival_date: date


class SupplierDeliveryHistoryRow(StrictFrozenModel):
    order_id: str
    supplier_id: str
    order_date: date
    delivery_date: date
    promised_lead_time_days: float = Field(gt=0)
    actual_lead_time_days: float = Field(gt=0)
    delay_days: float


class CalendarRow(StrictFrozenModel):
    calendar_date: date
    is_weekend: bool
    is_holiday: bool
    is_payday: bool


class RetailSnapshot(StrictFrozenModel):
    dataset_id: str
    store_id: str
    decision_date: date
    lookback_start_date: date
    horizon_end_date: date

    products: tuple[ProductSnapshot, ...]
    suppliers: tuple[SupplierSnapshot, ...]
    sales_history: tuple[SalesHistoryRow, ...]
    inventory: tuple[InventoryPosition, ...]
    outstanding_orders: tuple[OutstandingOrder, ...]
    supplier_delivery_history: tuple[
        SupplierDeliveryHistoryRow,
        ...,
    ]
    calendar: tuple[CalendarRow, ...]

    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_snapshot(self) -> "RetailSnapshot":
        if self.lookback_start_date > self.decision_date:
            raise ValueError(
                "lookback_start_date tidak boleh melewati decision_date"
            )

        if self.horizon_end_date <= self.decision_date:
            raise ValueError(
                "horizon_end_date harus setelah decision_date"
            )

        product_ids = [product.sku_id for product in self.products]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("sku_id pada products harus unik")

        supplier_ids = {
            supplier.supplier_id for supplier in self.suppliers
        }

        missing_suppliers = {
            product.supplier_id
            for product in self.products
            if product.supplier_id not in supplier_ids
        }
        if missing_suppliers:
            raise ValueError(
                "Supplier produk tidak ditemukan: "
                f"{sorted(missing_suppliers)}"
            )

        product_id_set = set(product_ids)

        inventory_ids = [
            position.sku_id for position in self.inventory
        ]
        if len(inventory_ids) != len(set(inventory_ids)):
            raise ValueError(
                "Setiap SKU hanya boleh memiliki satu inventory position"
            )

        if set(inventory_ids) != product_id_set:
            missing = product_id_set - set(inventory_ids)
            extra = set(inventory_ids) - product_id_set
            raise ValueError(
                "Inventory harus mencakup seluruh SKU. "
                f"Missing={sorted(missing)}, extra={sorted(extra)}"
            )

        for row in self.sales_history:
            if row.sku_id not in product_id_set:
                raise ValueError(
                    f"Sales history mengandung SKU asing: {row.sku_id}"
                )
            if row.sales_date > self.decision_date:
                raise ValueError(
                    "Sales history tidak boleh melewati decision_date"
                )

        for position in self.inventory:
            if position.as_of_date > self.decision_date:
                raise ValueError(
                    "Inventory as_of_date tidak boleh melewati "
                    "decision_date"
                )

        for order in self.outstanding_orders:
            if order.sku_id not in product_id_set:
                raise ValueError(
                    f"Outstanding order mengandung SKU asing: "
                    f"{order.sku_id}"
                )
            if order.supplier_id not in supplier_ids:
                raise ValueError(
                    f"Outstanding order mengandung supplier asing: "
                    f"{order.supplier_id}"
                )
            if order.order_date > self.decision_date:
                raise ValueError(
                    "Outstanding order tidak boleh dibuat setelah "
                    "decision_date"
                )

        for delivery in self.supplier_delivery_history:
            if delivery.supplier_id not in supplier_ids:
                raise ValueError(
                    f"Delivery history mengandung supplier asing: "
                    f"{delivery.supplier_id}"
                )
            if delivery.delivery_date > self.decision_date:
                raise ValueError(
                    "Supplier delivery outcome setelah decision_date "
                    "tidak boleh masuk snapshot"
                )

        calendar_dates = [
            row.calendar_date for row in self.calendar
        ]
        if len(calendar_dates) != len(set(calendar_dates)):
            raise ValueError("Tanggal calendar harus unik")

        if self.decision_date not in set(calendar_dates):
            raise ValueError(
                "Calendar harus mencakup decision_date"
            )

        if self.horizon_end_date not in set(calendar_dates):
            raise ValueError(
                "Calendar harus mencakup horizon_end_date"
            )

        return self

    def data_hash(self) -> str:
        payload = self.model_dump(mode="json")

        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        return hashlib.sha256(encoded).hexdigest()
