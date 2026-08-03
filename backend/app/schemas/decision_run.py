from pydantic import BaseModel
from typing import Optional, Literal

PolicyPreset = Literal["protect_cash", "balanced", "protect_availability"]
ConfidenceLevel = Literal["tinggi", "sedang", "rendah"]
RecommendationStatus = Literal["belum_diputuskan", "disetujui", "diedit", "ditolak"]


class DecisionConstraints(BaseModel):
    budget_rp: float
    horizon_days: int = 7
    min_fill_rate: Optional[float] = None
    protected_sku_ids: list[str] = []
    policy_preset: PolicyPreset = "balanced"


class ForecastPoint(BaseModel):
    date: str
    q10: float
    q50: float
    q90: float


class SKURecommendation(BaseModel):
    sku_id: str
    priority_rank: int
    recommended_qty: int
    required_cash_rp: float
    inventory_on_hand: int
    inventory_on_order: int
    effective_inventory: int
    forecast_q10: float
    forecast_q50: float
    forecast_q90: float
    forecast_daily_series: list[ForecastPoint]
    stockout_risk_before: float
    stockout_risk_after: float
    lmar_before_rp: float
    lmar_after_rp: float
    incremental_lmar_avoided_rp: float
    wcar_before_rp: float
    wcar_after_rp: float
    incremental_wcar_added_rp: float
    supplier_on_time_probability: float
    supplier_p90_lead_time_days: int
    expected_nov_contribution_rp: float
    confidence: ConfidenceLevel
    reason_codes: list[str]
    warnings: list[str] = []
    status: RecommendationStatus = "belum_diputuskan"


class RestockPlan(BaseModel):
    run_id: str
    model_version: str
    data_hash: str
    budget_allocated_rp: float
    expected_nov_contribution_rp: float
    estimated_lmar_avoided_rp: float
    estimated_wcar_added_rp: float
    estimated_fill_rate: float
    data_quality: str
    warnings: list[str] = []
    runtime_ms: int
    recommendations: list[SKURecommendation]


class DecisionRunRequest(BaseModel):
    dataset_id: str
    store_id: str
    decision_date: str
    budget_rp: float
    horizon_days: int = 7
    policy_preset: PolicyPreset = "balanced"
    min_fill_rate: Optional[float] = None
    protected_sku_ids: list[str] = []


class DecisionRunStatusResponse(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]