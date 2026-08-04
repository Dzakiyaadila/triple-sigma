from app.schemas.decision_run import (
    DecisionConstraints,
    DecisionRunRequest,
    SKURecommendation,
)


def test_policy_defaults_use_public_api_value():
    constraints = DecisionConstraints(budget_rp=1_000_000)
    request = DecisionRunRequest(
        dataset_id="restockiq-demo-v1",
        store_id="S01",
        decision_date="2026-07-28",
        budget_rp=1_000_000,
    )

    assert constraints.policy_preset == "seimbang"
    assert request.policy_preset == "seimbang"


def test_inventory_fields_accept_probability_weighted_values():
    recommendation = SKURecommendation(
        sku_id="SKU001",
        sku_name="Produk Uji",
        category="Sembako",
        priority_rank=1,
        recommended_qty=10,
        required_cash_rp=100_000,
        inventory_on_hand=4.0,
        inventory_on_order=10.0,
        effective_inventory=11.5,
        forecast_q10=12.0,
        forecast_q50=18.0,
        forecast_q90=25.0,
        stockout_risk_before=0.7,
        stockout_risk_after=0.2,
        lmar_before_rp=200_000,
        lmar_after_rp=50_000,
        incremental_lmar_avoided_rp=150_000,
        wcar_before_rp=20_000,
        wcar_after_rp=40_000,
        incremental_wcar_added_rp=20_000,
        supplier_name="Supplier Uji",
        supplier_note="Data uji",
        supplier_on_time_probability=0.75,
        supplier_p90_lead_time_days=4.5,
        expected_nov_contribution_rp=130_000,
        confidence="sedang",
        reason_codes=["risiko_stockout_tinggi"],
        reasoning_short="Alasan uji",
        reason_more="Alasan jumlah",
        reason_not_more="Alasan tidak lebih banyak",
    )

    assert recommendation.effective_inventory == 11.5
    assert recommendation.supplier_p90_lead_time_days == 4.5
    assert recommendation.forecast_daily_series == []