import pytest

from app.db.models import DecisionRun, Product
from app.services.decision_run_service import (
    confirm_run,
    update_recommendation,
)


class FakeProduct:
    def __init__(self, unit_cost_rp):
        self.unit_cost_rp = unit_cost_rp


class FakeRun:
    def __init__(self, budget_rp):
        self.budget_rp = budget_rp


class FakeDB:
    """DB palsu untuk testing tanpa koneksi database."""

    def __init__(self, run, product):
        self._run = run
        self._product = product

    def get(self, model, key):
        if model is DecisionRun:
            return self._run
        if model is Product:
            return self._product
        return None

    def query(self, *args, **kwargs):
        class FakeQuery:
            def filter_by(self, **kwargs):
                return self

            def first(self):
                return None

        return FakeQuery()

    def commit(self):
        pass


def test_approve_within_budget_succeeds():
    plan = {
        "run_id": "run_test",
        "recommendations": [
            {
                "sku_id": "SKU001",
                "recommended_qty": 10,
                "required_cash_rp": 100_000,
                "status": "belum_diputuskan",
            },
        ],
    }
    db = FakeDB(
        run=FakeRun(budget_rp=200_000),
        product=FakeProduct(unit_cost_rp=10_000),
    )

    result = update_recommendation(
        db,
        plan,
        "SKU001",
        "disetujui",
        adjusted_qty=10,
    )

    assert result["budget_allocated_rp"] <= 200_000
    assert result["budget_remaining_rp"] >= 0


def test_approve_exceeding_budget_raises_error():
    plan = {
        "run_id": "run_test",
        "recommendations": [
            {
                "sku_id": "SKU001",
                "recommended_qty": 100,
                "required_cash_rp": 1_000_000,
                "status": "belum_diputuskan",
            },
        ],
    }
    db = FakeDB(
        run=FakeRun(budget_rp=200_000),
        product=FakeProduct(unit_cost_rp=10_000),
    )

    with pytest.raises(ValueError, match="melebihi budget"):
        update_recommendation(
            db,
            plan,
            "SKU001",
            "disetujui",
            adjusted_qty=100,
        )


def test_approve_zero_quantity_raises_error():
    plan = {
        "run_id": "run_test",
        "recommendations": [
            {
                "sku_id": "SKU001",
                "recommended_qty": 0,
                "required_cash_rp": 0,
                "status": "belum_diputuskan",
            },
        ],
    }
    db = FakeDB(
        run=FakeRun(budget_rp=200_000),
        product=FakeProduct(unit_cost_rp=10_000),
    )

    with pytest.raises(
        ValueError,
        match="harus lebih dari 0 unit",
    ):
        update_recommendation(
            db,
            plan,
            "SKU001",
            "disetujui",
            adjusted_qty=0,
        )


def test_confirm_ignores_approved_zero_quantity():
    plan = {
        "run_id": "run_test",
        "recommendations": [
            {
                "sku_id": "SKU001",
                "recommended_qty": 0,
                "adjusted_qty": None,
                "required_cash_rp": 0,
                "status": "disetujui",
            },
            {
                "sku_id": "SKU002",
                "recommended_qty": 2,
                "adjusted_qty": None,
                "required_cash_rp": 20_000,
                "status": "disetujui",
            },
            {
                "sku_id": "SKU003",
                "recommended_qty": 5,
                "adjusted_qty": None,
                "required_cash_rp": 50_000,
                "status": "ditolak",
            },
        ],
    }

    result = confirm_run(plan)

    assert result["confirmed_count"] == 1
    assert result["total_cost_rp"] == 20_000
