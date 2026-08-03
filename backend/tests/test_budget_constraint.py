import pytest
from app.services.decision_run_service import update_recommendation
from app.db.models import Product, DecisionRun


class FakeProduct:
    def __init__(self, unit_cost_rp):
        self.unit_cost_rp = unit_cost_rp


class FakeRun:
    def __init__(self, budget_rp):
        self.budget_rp = budget_rp


class FakeDB:
    """DB palsu buat testing tanpa perlu koneksi database beneran."""
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
            {"sku_id": "SKU001", "recommended_qty": 10, "required_cash_rp": 100000, "status": "belum_diputuskan"},
        ],
    }
    db = FakeDB(run=FakeRun(budget_rp=200000), product=FakeProduct(unit_cost_rp=10000))

    result = update_recommendation(db, plan, "SKU001", "disetujui", adjusted_qty=10)

    assert result["budget_allocated_rp"] <= 200000
    assert result["budget_remaining_rp"] >= 0


def test_approve_exceeding_budget_raises_error():
    plan = {
        "run_id": "run_test",
        "recommendations": [
            {"sku_id": "SKU001", "recommended_qty": 100, "required_cash_rp": 1000000, "status": "belum_diputuskan"},
        ],
    }
    db = FakeDB(run=FakeRun(budget_rp=200000), product=FakeProduct(unit_cost_rp=10000))

    with pytest.raises(ValueError, match="melebihi budget"):
        update_recommendation(db, plan, "SKU001", "disetujui", adjusted_qty=100)