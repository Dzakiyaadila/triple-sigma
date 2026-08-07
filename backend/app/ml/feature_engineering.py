from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from app.ml.contracts import RetailSnapshot
from app.ml.oracle_guard import assert_oracle_safe_payload


IDENTIFIER_COLUMNS = (
    "store_id",
    "sku_id",
    "category",
    "supplier_id",
    "day_of_week",
)

SIGNAL_LAGS = (1, 2, 3, 7, 14, 21, 28)
SIGNAL_WINDOWS = (7, 14, 28)

STATIC_NUMERIC_FEATURES = (
    "promo_flag",
    "is_weekend",
    "is_holiday",
    "is_payday_week",
    "day_of_month",
    "month",
    "unit_cost_rp",
    "unit_price_rp",
    "margin_rp",
    "markup_ratio",
    "store_id_code",
    "sku_id_code",
    "category_code",
    "supplier_id_code",
    "day_of_week_code",
    "date_ordinal",
)


def signal_feature_names(prefix: str) -> tuple[str, ...]:
    lag_features = tuple(
        f"{prefix}_lag_{lag}"
        for lag in SIGNAL_LAGS
    )

    rolling_features: list[str] = []

    for window in SIGNAL_WINDOWS:
        rolling_features.extend(
            [
                f"{prefix}_roll_mean_{window}",
                f"{prefix}_roll_std_{window}",
                f"{prefix}_zero_rate_{window}",
            ]
        )

    return (
        *lag_features,
        *rolling_features,
        f"{prefix}_ewm_7",
        f"{prefix}_ewm_28",
        f"{prefix}_days_since_positive",
    )


RECONSTRUCTION_FEATURES = (
    *signal_feature_names("units_sold"),
    "past_stockout_rate_28",
    "stock_on_hand_start",
    *STATIC_NUMERIC_FEATURES,
)

FORECAST_FEATURES = (
    *signal_feature_names("reconstructed_demand"),
    *STATIC_NUMERIC_FEATURES,
)


def _days_since_positive(values: pd.Series) -> pd.Series:
    shifted = values.shift(1).fillna(0).to_numpy(float)

    output: list[float] = []
    days_since: int | None = None

    for value in shifted:
        if value > 0:
            days_since = 0
        elif days_since is None:
            days_since = len(output) + 1
        else:
            days_since += 1

        output.append(float(days_since))

    return pd.Series(output, index=values.index, dtype=float)


def snapshot_to_frame(snapshot: RetailSnapshot) -> pd.DataFrame:
    assert_oracle_safe_payload(snapshot)

    products = {
        product.sku_id: product
        for product in snapshot.products
    }

    calendar = {
        row.calendar_date: row
        for row in snapshot.calendar
    }

    records: list[dict[str, Any]] = []

    for row in snapshot.sales_history:
        product = products[row.sku_id]
        calendar_row = calendar.get(row.sales_date)

        day = pd.Timestamp(row.sales_date)

        records.append(
            {
                "date": day,
                "store_id": snapshot.store_id,
                "sku_id": row.sku_id,
                "category": product.category,
                "supplier_id": product.supplier_id,
                "units_sold": float(row.units_sold),
                "stock_on_hand_start": float(
                    row.stock_on_hand_start
                ),
                # Historical outcomes before decision_date are
                # permitted for censoring reconstruction.
                "historical_stockout_flag": bool(
                    row.stockout_flag
                ),
                "promo_flag": float(row.promo_flag),
                "is_weekend": float(
                    calendar_row.is_weekend
                    if calendar_row
                    else day.dayofweek >= 5
                ),
                "is_holiday": float(
                    calendar_row.is_holiday
                    if calendar_row
                    else False
                ),
                "is_payday_week": float(
                    calendar_row.is_payday
                    if calendar_row
                    else False
                ),
                "day_of_month": float(day.day),
                "month": float(day.month),
                "day_of_week": str(day.day_name()),
                "unit_cost_rp": float(product.unit_cost_rp),
                "unit_price_rp": float(product.unit_price_rp),
            }
        )

    frame = pd.DataFrame.from_records(records)

    if frame.empty:
        raise ValueError(
            f"Snapshot {snapshot.store_id} tidak memiliki histori penjualan"
        )

    frame = frame.sort_values(
        ["store_id", "sku_id", "date"],
        kind="stable",
    ).reset_index(drop=True)

    frame["margin_rp"] = (
        frame["unit_price_rp"] - frame["unit_cost_rp"]
    ).clip(lower=0)

    frame["markup_ratio"] = (
        frame["unit_price_rp"]
        / frame["unit_cost_rp"].replace(0, np.nan)
    )

    frame["date_ordinal"] = (
        frame["date"] - pd.Timestamp("1970-01-01")
    ).dt.days.astype(float)

    return frame


def snapshots_to_frame(
    snapshots: Iterable[RetailSnapshot],
) -> pd.DataFrame:
    frames = [
        snapshot_to_frame(snapshot)
        for snapshot in snapshots
    ]

    if not frames:
        raise ValueError("Tidak ada snapshot untuk membangun training frame")

    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(
            ["store_id", "sku_id", "date"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def fit_category_maps(
    frame: pd.DataFrame,
) -> dict[str, dict[str, int]]:
    mappings: dict[str, dict[str, int]] = {}

    for column in IDENTIFIER_COLUMNS:
        values = sorted(
            frame[column]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        mappings[column] = {
            value: index
            for index, value in enumerate(values)
        }

    return mappings


def apply_category_maps(
    frame: pd.DataFrame,
    mappings: dict[str, dict[str, int]],
) -> pd.DataFrame:
    output = frame.copy()

    for column in IDENTIFIER_COLUMNS:
        mapping = mappings.get(column, {})

        output[f"{column}_code"] = (
            output[column]
            .astype(str)
            .map(mapping)
            .fillna(-1)
            .astype(float)
        )

    return output


def add_signal_history_features(
    frame: pd.DataFrame,
    *,
    signal_column: str,
    prefix: str,
) -> pd.DataFrame:
    output = frame.sort_values(
        ["store_id", "sku_id", "date"],
        kind="stable",
    ).copy()

    keys = ["store_id", "sku_id"]
    grouped = output.groupby(keys, sort=False)

    for lag in SIGNAL_LAGS:
        output[f"{prefix}_lag_{lag}"] = (
            grouped[signal_column].shift(lag)
        )

    for window in SIGNAL_WINDOWS:
        output[f"{prefix}_roll_mean_{window}"] = (
            grouped[signal_column].transform(
                lambda values: (
                    values
                    .shift(1)
                    .rolling(window, min_periods=1)
                    .mean()
                )
            )
        )

        output[f"{prefix}_roll_std_{window}"] = (
            grouped[signal_column].transform(
                lambda values: (
                    values
                    .shift(1)
                    .rolling(window, min_periods=2)
                    .std()
                )
            )
        )

        output[f"{prefix}_zero_rate_{window}"] = (
            grouped[signal_column].transform(
                lambda values: (
                    values
                    .shift(1)
                    .eq(0)
                    .astype(float)
                    .rolling(window, min_periods=1)
                    .mean()
                )
            )
        )

    output[f"{prefix}_ewm_7"] = (
        grouped[signal_column].transform(
            lambda values: (
                values
                .shift(1)
                .ewm(
                    span=7,
                    adjust=False,
                    min_periods=1,
                )
                .mean()
            )
        )
    )

    output[f"{prefix}_ewm_28"] = (
        grouped[signal_column].transform(
            lambda values: (
                values
                .shift(1)
                .ewm(
                    span=28,
                    adjust=False,
                    min_periods=1,
                )
                .mean()
            )
        )
    )

    output[f"{prefix}_days_since_positive"] = (
        grouped[signal_column].transform(
            _days_since_positive
        )
    )

    return output


def prepare_reconstruction_frame(
    frame: pd.DataFrame,
    mappings: dict[str, dict[str, int]],
) -> pd.DataFrame:
    output = apply_category_maps(frame, mappings)

    output = add_signal_history_features(
        output,
        signal_column="units_sold",
        prefix="units_sold",
    )

    output["past_stockout_rate_28"] = (
        output.groupby(
            ["store_id", "sku_id"],
            sort=False,
        )["historical_stockout_flag"]
        .transform(
            lambda values: (
                values
                .shift(1)
                .astype(float)
                .rolling(28, min_periods=1)
                .mean()
            )
        )
    )

    return output


def prepare_forecast_frame(
    frame: pd.DataFrame,
    mappings: dict[str, dict[str, int]],
) -> pd.DataFrame:
    if "reconstructed_demand" not in frame.columns:
        raise ValueError(
            "reconstructed_demand belum tersedia pada forecast frame"
        )

    output = apply_category_maps(frame, mappings)

    return add_signal_history_features(
        output,
        signal_column="reconstructed_demand",
        prefix="reconstructed_demand",
    )


def add_forward_target(
    frame: pd.DataFrame,
    *,
    signal_column: str,
    horizon_days: int,
    target_column: str,
) -> pd.DataFrame:
    if horizon_days < 1:
        raise ValueError("horizon_days harus minimal 1")

    output = frame.copy()
    keys = ["store_id", "sku_id"]

    def _forward_sum(values: pd.Series) -> pd.Series:
        shifted = pd.concat(
            [
                values.shift(-step)
                for step in range(1, horizon_days + 1)
            ],
            axis=1,
        )

        return shifted.sum(
            axis=1,
            min_count=horizon_days,
        )

    output[target_column] = (
        output.groupby(keys, sort=False)[signal_column]
        .transform(_forward_sum)
    )

    return output


def prepare_matrix(
    frame: pd.DataFrame,
    feature_columns: tuple[str, ...],
    medians: dict[str, float] | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    missing = [
        column
        for column in feature_columns
        if column not in frame.columns
    ]

    if missing:
        raise ValueError(
            f"Feature columns tidak tersedia: {missing}"
        )

    matrix = (
        frame.loc[:, feature_columns]
        .replace([np.inf, -np.inf], np.nan)
        .apply(pd.to_numeric, errors="coerce")
    )

    if medians is None:
        learned_medians = {
            column: float(value)
            for column, value in (
                matrix
                .median(numeric_only=True)
                .fillna(0)
                .items()
            )
        }
    else:
        learned_medians = {
            column: float(medians.get(column, 0))
            for column in feature_columns
        }

    matrix = (
        matrix
        .fillna(learned_medians)
        .fillna(0)
        .astype(float)
    )

    return matrix, learned_medians
