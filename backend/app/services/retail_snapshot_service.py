from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.orm import Session

from app.ml.contracts import (
    CalendarRow,
    InventoryPosition,
    OutstandingOrder,
    ProductSnapshot,
    RetailSnapshot,
    SalesHistoryRow,
    SupplierDeliveryHistoryRow,
    SupplierSnapshot,
)
from app.ml.oracle_guard import assert_oracle_safe_payload


class SnapshotBuildError(ValueError):
    """Raised when source data cannot produce a valid snapshot."""


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if value is None:
        raise SnapshotBuildError("Nilai tanggal tidak boleh kosong")

    return date.fromisoformat(str(value)[:10])


def _to_float(
    value: Any,
    default: float = 0.0,
) -> float:
    if value is None:
        return default

    number = float(value)

    if math.isnan(number) or math.isinf(number):
        return default

    return number


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return bool(value)

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "ya",
    }


def _column(
    table: Table,
    *candidate_names: str,
    required: bool = True,
):
    for name in candidate_names:
        if name in table.c:
            return table.c[name]

    if required:
        raise SnapshotBuildError(
            f"Tabel '{table.name}' tidak memiliki salah satu kolom: "
            f"{candidate_names}"
        )

    return None


def _mapping_value(
    row: Any,
    column: Any,
    default: Any = None,
) -> Any:
    if column is None:
        return default

    return row[column.name]


def _stable_order_id(
    *,
    store_id: str,
    sku_id: str,
    supplier_id: str,
    order_date: date,
    quantity: float,
    row_index: int,
) -> str:
    raw = (
        f"{store_id}|{sku_id}|{supplier_id}|"
        f"{order_date.isoformat()}|{quantity}|{row_index}"
    )

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"po_{digest}"


def build_retail_snapshot(
    db: Session,
    *,
    store_id: str,
    decision_date: date,
    horizon_days: int,
    lookback_days: int = 182,
) -> RetailSnapshot:
    if horizon_days < 1:
        raise SnapshotBuildError(
            "horizon_days harus minimal 1"
        )

    if lookback_days < 1:
        raise SnapshotBuildError(
            "lookback_days harus minimal 1"
        )

    lookback_start = (
        decision_date - timedelta(days=lookback_days - 1)
    )
    horizon_end = (
        decision_date + timedelta(days=horizon_days)
    )

    bind = db.get_bind()
    metadata = MetaData()

    stores_table = Table(
        "dim_stores",
        metadata,
        autoload_with=bind,
    )
    products_table = Table(
        "dim_products",
        metadata,
        autoload_with=bind,
    )
    suppliers_table = Table(
        "dim_suppliers",
        metadata,
        autoload_with=bind,
    )
    sales_table = Table(
        "fact_daily_sales",
        metadata,
        autoload_with=bind,
    )
    purchase_orders_table = Table(
        "fact_purchase_orders",
        metadata,
        autoload_with=bind,
    )
    calendar_table = Table(
        "dim_calendar",
        metadata,
        autoload_with=bind,
    )

    warnings: list[str] = []

    if lookback_days < horizon_days:
        warnings.append(
            "Periode histori lebih pendek daripada horizon forecast; "
            "confidence dapat diturunkan untuk SKU dengan data terbatas."
        )

    # Store validation
    store_id_col = _column(
        stores_table,
        "store_id",
    )

    store_exists = db.execute(
        select(store_id_col).where(
            store_id_col == store_id
        )
    ).first()

    if store_exists is None:
        raise SnapshotBuildError(
            f"Toko {store_id} tidak ditemukan"
        )

    # Suppliers
    supplier_id_col = _column(
        suppliers_table,
        "supplier_id",
    )
    supplier_name_col = _column(
        suppliers_table,
        "supplier_name",
        "name",
    )
    supplier_promised_col = _column(
        suppliers_table,
        "promised_lead_time_days",
        "lead_time_days",
    )

    supplier_rows = db.execute(
        select(
            supplier_id_col,
            supplier_name_col,
            supplier_promised_col,
        ).order_by(supplier_id_col)
    ).mappings().all()

    suppliers = tuple(
        SupplierSnapshot(
            supplier_id=str(
                _mapping_value(row, supplier_id_col)
            ),
            supplier_name=str(
                _mapping_value(row, supplier_name_col)
            ),
            promised_lead_time_days=_to_float(
                _mapping_value(
                    row,
                    supplier_promised_col,
                )
            ),
        )
        for row in supplier_rows
    )

    supplier_by_id = {
        supplier.supplier_id: supplier
        for supplier in suppliers
    }

    # Products
    product_sku_col = _column(
        products_table,
        "sku_id",
    )
    product_name_col = _column(
        products_table,
        "product_name",
        "sku_name",
        "name",
    )
    product_category_col = _column(
        products_table,
        "category",
        "product_category",
    )
    product_supplier_col = _column(
        products_table,
        "supplier_id",
    )
    unit_cost_col = _column(
        products_table,
        "unit_cost_rp",
        "unit_cost",
    )
    unit_price_col = _column(
        products_table,
        "unit_price_rp",
        "unit_price",
    )

    product_rows = db.execute(
        select(
            product_sku_col,
            product_name_col,
            product_category_col,
            product_supplier_col,
            unit_cost_col,
            unit_price_col,
        ).order_by(product_sku_col)
    ).mappings().all()

    products = tuple(
        ProductSnapshot(
            sku_id=str(
                _mapping_value(row, product_sku_col)
            ),
            product_name=str(
                _mapping_value(row, product_name_col)
            ),
            category=str(
                _mapping_value(row, product_category_col)
            ),
            supplier_id=str(
                _mapping_value(row, product_supplier_col)
            ),
            unit_cost_rp=_to_float(
                _mapping_value(row, unit_cost_col)
            ),
            unit_price_rp=_to_float(
                _mapping_value(row, unit_price_col)
            ),
        )
        for row in product_rows
    )

    product_by_id = {
        product.sku_id: product
        for product in products
    }

    # Historical sales: explicitly select safe columns only.
    sales_store_col = _column(
        sales_table,
        "store_id",
    )
    sales_sku_col = _column(
        sales_table,
        "sku_id",
    )
    sales_date_col = _column(
        sales_table,
        "sales_date",
        "transaction_date",
        "calendar_date",
        "date",
    )
    units_sold_col = _column(
        sales_table,
        "units_sold",
    )
    stock_start_col = _column(
        sales_table,
        "stock_on_hand_start",
        "stock_start",
    )
    stock_end_col = _column(
        sales_table,
        "stock_on_hand_end",
        "stock_end",
    )
    stockout_col = _column(
        sales_table,
        "stockout_flag",
        "is_stockout",
        required=False,
    )
    promo_col = _column(
        sales_table,
        "promo_flag",
        "is_promo",
        required=False,
    )

    safe_sales_columns = [
        sales_sku_col,
        sales_date_col,
        units_sold_col,
        stock_start_col,
        stock_end_col,
    ]

    if stockout_col is not None:
        safe_sales_columns.append(stockout_col)

    if promo_col is not None:
        safe_sales_columns.append(promo_col)

    sales_rows = db.execute(
        select(*safe_sales_columns)
        .where(sales_store_col == store_id)
        .where(sales_date_col >= lookback_start)
        .where(sales_date_col <= decision_date)
        .order_by(sales_date_col, sales_sku_col)
    ).mappings().all()

    sales_history_list: list[SalesHistoryRow] = []
    latest_inventory_by_sku: dict[
        str,
        InventoryPosition,
    ] = {}

    for row in sales_rows:
        sku_id = str(
            _mapping_value(row, sales_sku_col)
        )
        sales_day = _to_date(
            _mapping_value(row, sales_date_col)
        )
        stock_end = _to_float(
            _mapping_value(row, stock_end_col)
        )

        stockout_flag = (
            _to_bool(
                _mapping_value(row, stockout_col)
            )
            if stockout_col is not None
            else stock_end <= 0
        )

        sales_record = SalesHistoryRow(
            sku_id=sku_id,
            sales_date=sales_day,
            units_sold=_to_float(
                _mapping_value(row, units_sold_col)
            ),
            stock_on_hand_start=_to_float(
                _mapping_value(row, stock_start_col)
            ),
            stock_on_hand_end=stock_end,
            stockout_flag=stockout_flag,
            promo_flag=_to_bool(
                _mapping_value(row, promo_col)
            ),
        )

        sales_history_list.append(sales_record)

        latest_inventory_by_sku[sku_id] = (
            InventoryPosition(
                sku_id=sku_id,
                on_hand=stock_end,
                as_of_date=sales_day,
            )
        )

    for product in products:
        if product.sku_id not in latest_inventory_by_sku:
            warnings.append(
                f"Tidak ada histori stok untuk {product.sku_id}; "
                "inventory diasumsikan 0."
            )
            latest_inventory_by_sku[product.sku_id] = (
                InventoryPosition(
                    sku_id=product.sku_id,
                    on_hand=0,
                    as_of_date=decision_date,
                )
            )

    inventory = tuple(
        latest_inventory_by_sku[product.sku_id]
        for product in products
    )

    # Purchase-order reconstruction as of decision_date.
    po_store_col = _column(
        purchase_orders_table,
        "store_id",
        required=False,
    )
    po_id_col = _column(
        purchase_orders_table,
        "purchase_order_id",
        "po_id",
        "order_id",
        required=False,
    )
    po_sku_col = _column(
        purchase_orders_table,
        "sku_id",
    )
    po_supplier_col = _column(
        purchase_orders_table,
        "supplier_id",
        required=False,
    )
    po_order_date_col = _column(
        purchase_orders_table,
        "order_date",
        "po_date",
        "date",
    )
    po_qty_col = _column(
        purchase_orders_table,
        "order_qty_units",
        "order_quantity",
        "quantity",
    )
    po_promised_col = _column(
        purchase_orders_table,
        "promised_lead_time_days",
        required=False,
    )
    po_actual_col = _column(
        purchase_orders_table,
        "actual_lead_time_days",
        required=False,
    )
    po_delay_col = _column(
        purchase_orders_table,
        "delay_days",
        required=False,
    )

    safe_po_columns = [
        po_sku_col,
        po_order_date_col,
        po_qty_col,
    ]

    for optional_column in (
        po_store_col,
        po_id_col,
        po_supplier_col,
        po_promised_col,
        po_actual_col,
        po_delay_col,
    ):
        if (
            optional_column is not None
            and optional_column not in safe_po_columns
        ):
            safe_po_columns.append(optional_column)

    po_statement = (
        select(*safe_po_columns)
        .where(po_order_date_col <= decision_date)
        .order_by(po_order_date_col, po_sku_col)
    )

    if po_store_col is not None:
        po_statement = po_statement.where(
            po_store_col == store_id
        )
    else:
        warnings.append(
            "fact_purchase_orders tidak memiliki store_id; "
            "PO diperlakukan sebagai data global."
        )

    po_rows = db.execute(
        po_statement
    ).mappings().all()

    outstanding_orders: list[OutstandingOrder] = []
    supplier_delivery_history: list[
        SupplierDeliveryHistoryRow
    ] = []

    for row_index, row in enumerate(po_rows):
        sku_id = str(
            _mapping_value(row, po_sku_col)
        )

        product = product_by_id.get(sku_id)
        if product is None:
            warnings.append(
                f"PO untuk SKU asing {sku_id} dilewati."
            )
            continue

        supplier_id = str(
            _mapping_value(
                row,
                po_supplier_col,
                product.supplier_id,
            )
        )

        supplier = supplier_by_id.get(supplier_id)
        if supplier is None:
            warnings.append(
                f"PO {sku_id} menggunakan supplier asing "
                f"{supplier_id}; baris dilewati."
            )
            continue

        order_day = _to_date(
            _mapping_value(row, po_order_date_col)
        )
        quantity = _to_float(
            _mapping_value(row, po_qty_col)
        )

        if quantity <= 0:
            continue

        promised_lead = _to_float(
            _mapping_value(
                row,
                po_promised_col,
                supplier.promised_lead_time_days,
            )
        )

        actual_lead_raw = _mapping_value(
            row,
            po_actual_col,
            None,
        )
        actual_lead = (
            _to_float(actual_lead_raw)
            if actual_lead_raw is not None
            else None
        )

        delay_days = _to_float(
            _mapping_value(
                row,
                po_delay_col,
                (
                    actual_lead - promised_lead
                    if actual_lead is not None
                    else 0
                ),
            )
        )

        explicit_order_id = _mapping_value(
            row,
            po_id_col,
            None,
        )

        order_id = (
            str(explicit_order_id)
            if explicit_order_id is not None
            else _stable_order_id(
                store_id=store_id,
                sku_id=sku_id,
                supplier_id=supplier_id,
                order_date=order_day,
                quantity=quantity,
                row_index=row_index,
            )
        )

        expected_arrival = (
            order_day
            + timedelta(
                days=max(1, math.ceil(promised_lead))
            )
        )

        delivery_date = (
            order_day
            + timedelta(
                days=max(1, math.ceil(actual_lead))
            )
            if actual_lead is not None
            and actual_lead > 0
            else None
        )

        delivered_by_cutoff = (
            delivery_date is not None
            and delivery_date <= decision_date
        )

        if delivered_by_cutoff:
            supplier_delivery_history.append(
                SupplierDeliveryHistoryRow(
                    order_id=order_id,
                    supplier_id=supplier_id,
                    order_date=order_day,
                    delivery_date=delivery_date,
                    promised_lead_time_days=promised_lead,
                    actual_lead_time_days=actual_lead,
                    delay_days=delay_days,
                )
            )
        else:
            # Actual future lead-time outcome is deliberately not
            # copied into the outstanding-order snapshot.
            outstanding_orders.append(
                OutstandingOrder(
                    order_id=order_id,
                    sku_id=sku_id,
                    supplier_id=supplier_id,
                    order_date=order_day,
                    order_qty_units=quantity,
                    promised_lead_time_days=promised_lead,
                    expected_arrival_date=expected_arrival,
                )
            )

    # Calendar covariates are known in advance and may extend
    # beyond decision_date through the forecast horizon.
    calendar_date_col = _column(
        calendar_table,
        "calendar_date",
        "date",
    )

    calendar_min_date, calendar_max_date = db.execute(
        select(
            func.min(calendar_date_col),
            func.max(calendar_date_col),
        )
    ).one()

    if calendar_min_date is None or calendar_max_date is None:
        raise SnapshotBuildError(
            "dim_calendar kosong; snapshot tidak dapat dibuat"
        )

    calendar_min_date = _to_date(calendar_min_date)
    calendar_max_date = _to_date(calendar_max_date)

    latest_valid_decision_date = (
        calendar_max_date - timedelta(days=horizon_days)
    )

    if not (
        calendar_min_date
        <= decision_date
        <= latest_valid_decision_date
    ):
        raise SnapshotBuildError(
            f"decision_date {decision_date.isoformat()} di luar rentang "
            f"valid untuk horizon {horizon_days} hari. "
            f"Gunakan tanggal antara "
            f"{calendar_min_date.isoformat()} dan "
            f"{latest_valid_decision_date.isoformat()}."
        )

    weekend_col = _column(
        calendar_table,
        "is_weekend",
        "weekend_flag",
        required=False,
    )
    holiday_col = _column(
        calendar_table,
        "is_holiday",
        "holiday_flag",
        required=False,
    )
    payday_col = _column(
        calendar_table,
        "is_payday",
        "payday_flag",
        required=False,
    )

    safe_calendar_columns = [calendar_date_col]

    for optional_column in (
        weekend_col,
        holiday_col,
        payday_col,
    ):
        if optional_column is not None:
            safe_calendar_columns.append(optional_column)

    calendar_rows = db.execute(
        select(*safe_calendar_columns)
        .where(calendar_date_col >= lookback_start)
        .where(calendar_date_col <= horizon_end)
        .order_by(calendar_date_col)
    ).mappings().all()

    calendar = tuple(
        CalendarRow(
            calendar_date=_to_date(
                _mapping_value(row, calendar_date_col)
            ),
            is_weekend=_to_bool(
                _mapping_value(row, weekend_col)
            ),
            is_holiday=_to_bool(
                _mapping_value(row, holiday_col)
            ),
            is_payday=_to_bool(
                _mapping_value(row, payday_col)
            ),
        )
        for row in calendar_rows
    )

    snapshot = RetailSnapshot(
        store_id=store_id,
        decision_date=decision_date,
        lookback_start_date=lookback_start,
        horizon_end_date=horizon_end,
        products=products,
        suppliers=suppliers,
        sales_history=tuple(sales_history_list),
        inventory=inventory,
        outstanding_orders=tuple(
            sorted(
                outstanding_orders,
                key=lambda order: (
                    order.expected_arrival_date,
                    order.sku_id,
                    order.order_id,
                ),
            )
        ),
        supplier_delivery_history=tuple(
            sorted(
                supplier_delivery_history,
                key=lambda delivery: (
                    delivery.delivery_date,
                    delivery.supplier_id,
                    delivery.order_id,
                ),
            )
        ),
        calendar=calendar,
        warnings=tuple(sorted(set(warnings))),
    )

    assert_oracle_safe_payload(snapshot)

    return snapshot
