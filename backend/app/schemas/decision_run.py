from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Literal

PolicyPreset = Literal["lindungi_kas", "seimbang", "lindungi_ketersediaan"]
ConfidenceLevel = Literal["tinggi", "sedang", "rendah"]
RecommendationStatus = Literal["belum_diputuskan", "disetujui", "diedit", "ditolak"]


class DecisionConstraints(BaseModel):
    budget_rp: float = Field(ge=0)
    horizon_days: int = 7
    min_fill_rate: Optional[float] = None
    protected_sku_ids: list[str] = Field(default_factory=list)
    policy_preset: PolicyPreset = Field(
        default="seimbang",
        validate_default=True,
    )


class ForecastPoint(BaseModel):
    date: str
    q10: float
    q50: float
    q90: float



class SKURecommendation(BaseModel):
    sku_id: str
    sku_name: str
    category: str
    priority_rank: int
    recommended_qty: int
    required_cash_rp: float
    inventory_on_hand: float
    inventory_on_order: float
    effective_inventory: float
    forecast_q10: float
    forecast_q50: float
    forecast_q90: float
    forecast_daily_series: list[ForecastPoint] = Field(default_factory=list)
    stockout_risk_before: float
    stockout_risk_after: float
    lmar_before_rp: float
    lmar_after_rp: float
    incremental_lmar_avoided_rp: float
    wcar_before_rp: float
    wcar_after_rp: float
    incremental_wcar_added_rp: float
    supplier_name: str
    supplier_note: str
    supplier_on_time_probability: float
    supplier_p90_lead_time_days: float
    expected_nov_contribution_rp: float
    confidence: ConfidenceLevel
    reason_codes: list[str]
    reasoning_short: str
    reason_more: str
    reason_not_more: str
    warnings: list[str] = Field(default_factory=list)
    status: RecommendationStatus = "belum_diputuskan"


class RestockPlan(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    run_id: str
    model_version: str
    data_hash: str
    budget_allocated_rp: float
    expected_nov_contribution_rp: float
    estimated_lmar_avoided_rp: float
    estimated_wcar_added_rp: float
    estimated_fill_rate: float
    data_quality: str
    warnings: list[str] = Field(default_factory=list)
    runtime_ms: int
    recommendations: list[SKURecommendation]


class DecisionRunRequest(BaseModel):
    dataset_id: str
    store_id: str
    decision_date: str
    budget_rp: float = Field(ge=0)
    horizon_days: int = 7
    policy_preset: PolicyPreset = Field(
        default="seimbang",
        validate_default=True,
    )
    min_fill_rate: Optional[float] = None
    protected_sku_ids: list[str] = Field(default_factory=list)


class DecisionRunStatusResponse(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]


class RecommendationUpdateRequest(BaseModel):
    status: RecommendationStatus
    adjusted_qty: Optional[int] = None
    user_note: Optional[str] = None


class RecommendationUpdateResponse(BaseModel):
    sku_id: str
    status: RecommendationStatus
    adjusted_qty: Optional[int]
    required_cash_rp: float
    budget_allocated_rp: float
    budget_remaining_rp: float


class ConfirmResponse(BaseModel):
    confirmed_count: int
    confirmed_at: str
    total_cost_rp: float
