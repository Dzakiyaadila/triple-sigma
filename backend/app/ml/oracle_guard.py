from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel


ORACLE_FORBIDDEN_FIELDS = frozenset(
    {
        "units_demanded_est",
        "demand_profile",
        "avg_daily_demand_per_store",
        "cash_locked_in_stock_rp",
    }
)


class OracleFieldError(ValueError):
    """Raised when an evaluation-only field enters prediction input."""


def assert_oracle_safe_payload(
    payload: Any,
    path: str = "$",
) -> None:
    if isinstance(payload, BaseModel):
        assert_oracle_safe_payload(
            payload.model_dump(mode="python"),
            path=path,
        )
        return

    if isinstance(payload, Mapping):
        for raw_key, value in payload.items():
            key = str(raw_key)
            normalized_key = key.strip().lower()

            if normalized_key in ORACLE_FORBIDDEN_FIELDS:
                raise OracleFieldError(
                    f"Oracle field '{key}' ditemukan di {path}"
                )

            assert_oracle_safe_payload(
                value,
                path=f"{path}.{key}",
            )

        return

    if isinstance(payload, Sequence) and not isinstance(
        payload,
        (str, bytes, bytearray),
    ):
        for index, value in enumerate(payload):
            assert_oracle_safe_payload(
                value,
                path=f"{path}[{index}]",
            )