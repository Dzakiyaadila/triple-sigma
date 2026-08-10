from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from app.ml.contracts import RetailSnapshot
from app.ml.oracle_guard import assert_oracle_safe_payload

LAGS = (1, 2, 3, 7, 14, 21, 28)
WINDOWS = (7, 14, 28)

RECONSTRUCTION_FEATURES = (
    *(f"lag_{lag}" for lag in LAGS),
    *(f"roll_mean_{window}" for window in WINDOWS),
    *(f"roll_std_{window}" for window in WINDOWS),
    *(f"zero_rate_{window}" for window in WINDOWS),
    "ewm_7",
    "ewm_28",
    "past_stockout_rate_28",
    "promo_flag",
    "is_weekend",
    "is_holiday",
    "is_payday_week",
    "day_of_month",
    "month",
    "unit_cost_rp",
    "unit_price_rp",
    "margin_rp",
    "shelf_life_days",
    "is_perishable",
    "promised_lead_time_days",
)

FORECAST_FEATURES = (
    *(f"sig_lag_{lag}" for lag in LAGS),
    *(f"sig_roll_mean_{window}" for window in WINDOWS),
    *(f"sig_roll_std_{window}" for window in WINDOWS),
    *(f"sig_zero_rate_{window}" for window in WINDOWS),
    "promo_flag",
    "is_weekend",
    "is_holiday",
    "is_payday_week",
    "day_of_month",
    "month",
    "unit_cost_rp",
    "unit_price_rp",
    "margin_rp",
    "shelf_life_days",
    "is_perishable",
    "promised_lead_time_days",
)


def snapshot_to_frame(snapshot: RetailSnapshot) -> pd.DataFrame:
    """Convert an Oracle-safe snapshot to a production feature frame."""
    assert_oracle_safe_payload(snapshot)

    products = {product.sku_id: product for product in snapshot.products}
    suppliers = {
        supplier.supplier_id: supplier for supplier in snapshot.suppliers
    }
    calendar = {row.calendar_date: row for row in snapshot.calendar}

    records: list[dict[str, Any]] = []
    for row in snapshot.sales_history:
        product = products[row.sku_id]
        supplier = suppliers[product.supplier_id]
        day = pd.Timestamp(row.sales_date)
        calendar_row = calendar.get(row.sales_date)

        records.append(
            {
                "date": day,
                "store_id": snapshot.store_id,
                "sku_id": row.sku_id,
                "units_sold": float(row.units_sold),
                "stock_on_hand_start": float(row.stock_on_hand_start),
                "stockout_flag": bool(row.stockout_flag),
                "promo_flag": float(row.promo_flag),
                "is_weekend": float(
                    calendar_row.is_weekend
                    if calendar_row is not None
                    else day.dayofweek >= 5
                ),
                "is_holiday": float(
                    calendar_row.is_holiday if calendar_row is not None else False
                ),
                "is_payday_week": float(
                    calendar_row.is_payday_week
                    if calendar_row is not None
                    else False
                ),
                "day_of_month": float(day.day),
                "month": float(day.month),
                "unit_cost_rp": float(product.unit_cost_rp),
                "unit_price_rp": float(product.unit_price_rp),
                "shelf_life_days": float(product.shelf_life_days),
                "is_perishable": float(product.is_perishable),
                "promised_lead_time_days": float(
                    supplier.promised_lead_time_days
                ),
            }
        )

    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        raise ValueError(
            f"Snapshot {snapshot.dataset_id}/{snapshot.store_id} "
            "tidak memiliki histori penjualan"
        )

    frame["margin_rp"] = (
        frame["unit_price_rp"] - frame["unit_cost_rp"]
    ).clip(lower=0)

    return frame.sort_values(
        ["store_id", "sku_id", "date"], kind="stable"
    ).reset_index(drop=True)


def snapshots_to_frame(snapshots: Iterable[RetailSnapshot]) -> pd.DataFrame:
    frames = [snapshot_to_frame(snapshot) for snapshot in snapshots]
    if not frames:
        raise ValueError("Tidak ada snapshot untuk training")
    return pd.concat(frames, ignore_index=True).sort_values(
        ["store_id", "sku_id", "date"], kind="stable"
    ).reset_index(drop=True)


def add_reconstruction_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Causal reconstruction features; every history feature is shifted."""
    x = frame.sort_values(["store_id", "sku_id", "date"], kind="stable").copy()
    group = x.groupby(["store_id", "sku_id"], sort=False)

    for lag in LAGS:
        x[f"lag_{lag}"] = group["units_sold"].shift(lag)

    shifted = group["units_sold"].shift(1)
    for window in WINDOWS:
        grouped = shifted.groupby([x["store_id"], x["sku_id"]])
        x[f"roll_mean_{window}"] = (
            grouped.rolling(window, min_periods=1)
            .mean()
            .reset_index(level=[0, 1], drop=True)
        )
        x[f"roll_std_{window}"] = (
            grouped.rolling(window, min_periods=2)
            .std()
            .reset_index(level=[0, 1], drop=True)
        )
        x[f"zero_rate_{window}"] = (
            shifted.eq(0)
            .astype(float)
            .groupby([x["store_id"], x["sku_id"]])
            .rolling(window, min_periods=1)
            .mean()
            .reset_index(level=[0, 1], drop=True)
        )

    x["ewm_7"] = group["units_sold"].transform(
        lambda series: series.shift(1).ewm(
            span=7, adjust=False, min_periods=1
        ).mean()
    )
    x["ewm_28"] = group["units_sold"].transform(
        lambda series: series.shift(1).ewm(
            span=28, adjust=False, min_periods=1
        ).mean()
    )
    x["past_stockout_rate_28"] = group["stockout_flag"].transform(
        lambda series: series.shift(1).astype(float).rolling(
            28, min_periods=1
        ).mean()
    )
    return x


def add_forecast_features(
    frame: pd.DataFrame,
    *,
    signal_col: str = "reconstructed_demand",
) -> pd.DataFrame:
    """Causal features for direct cumulative forecasting."""
    if signal_col not in frame.columns:
        raise ValueError(f"Signal forecast tidak tersedia: {signal_col}")

    x = frame.sort_values(["store_id", "sku_id", "date"], kind="stable").copy()
    group = x.groupby(["store_id", "sku_id"], sort=False)

    for lag in LAGS:
        x[f"sig_lag_{lag}"] = group[signal_col].shift(lag)

    shifted = group[signal_col].shift(1)
    for window in WINDOWS:
        grouped = shifted.groupby([x["store_id"], x["sku_id"]])
        x[f"sig_roll_mean_{window}"] = (
            grouped.rolling(window, min_periods=1)
            .mean()
            .reset_index(level=[0, 1], drop=True)
        )
        x[f"sig_roll_std_{window}"] = (
            grouped.rolling(window, min_periods=2)
            .std()
            .reset_index(level=[0, 1], drop=True)
        )
        x[f"sig_zero_rate_{window}"] = (
            shifted.eq(0)
            .astype(float)
            .groupby([x["store_id"], x["sku_id"]])
            .rolling(window, min_periods=1)
            .mean()
            .reset_index(level=[0, 1], drop=True)
        )
    return x


def add_forward_target(
    frame: pd.DataFrame,
    *,
    signal_col: str,
    horizon_days: int,
    target_col: str,
) -> pd.DataFrame:
    """Sum t+1..t+H only; the origin day's signal is never in its label."""
    if horizon_days < 1:
        raise ValueError("horizon_days harus minimal 1")

    x = frame.copy()

    def future_sum(series: pd.Series) -> pd.Series:
        shifted = pd.concat(
            [series.shift(-step) for step in range(1, horizon_days + 1)],
            axis=1,
        )
        return shifted.sum(axis=1, min_count=horizon_days)

    x[target_col] = x.groupby(
        ["store_id", "sku_id"], sort=False
    )[signal_col].transform(future_sum)
    return x


def prepare_matrix(
    frame: pd.DataFrame,
    feature_columns: tuple[str, ...],
    medians: dict[str, float] | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    missing = [column for column in feature_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Feature columns tidak tersedia: {missing}")

    matrix = frame.loc[:, feature_columns].replace(
        [np.inf, -np.inf], np.nan
    ).apply(pd.to_numeric, errors="coerce")

    learned = (
        {
            column: float(value)
            for column, value in matrix.median(numeric_only=True).fillna(0).items()
        }
        if medians is None
        else {column: float(medians.get(column, 0.0)) for column in feature_columns}
    )

    return matrix.fillna(learned).fillna(0.0).astype(float), learned
