from sqlalchemy import Column, String, Integer, Float, Boolean, Date, DateTime, JSON, ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# ============================================
# TABEL SUMBER DATA (dari dataset ML)
# ============================================

class Store(Base):
    __tablename__ = "dim_stores"
    store_id = Column(String, primary_key=True)
    store_name = Column(String, nullable=False)
    city = Column(String)
    store_type = Column(String)
    cluster = Column(String)


class Supplier(Base):
    __tablename__ = "dim_suppliers"
    supplier_id = Column(String, primary_key=True)
    supplier_name = Column(String)
    promised_lead_time_days = Column(Integer)


class Product(Base):
    __tablename__ = "dim_products"
    sku_id = Column(String, primary_key=True)
    product_name = Column(String, nullable=False)
    category = Column(String)
    demand_profile = Column(String)          # Oracle — jangan jadi input model
    avg_daily_demand_per_store = Column(Float)  # Oracle
    unit_cost_rp = Column(Float)
    unit_price_rp = Column(Float)
    shelf_life_days = Column(Integer)
    is_perishable = Column(Boolean)
    lead_time_days_default = Column(Integer)
    supplier_id = Column(String, ForeignKey("dim_suppliers.supplier_id"))


class CalendarDay(Base):
    __tablename__ = "dim_calendar"
    date = Column(Date, primary_key=True)
    day_of_week = Column(String)
    is_weekend = Column(Boolean)
    is_holiday = Column(Boolean)
    day_of_month = Column(Integer)
    is_payday_week = Column(Boolean)
    month = Column(Integer)


class DailySales(Base):
    __tablename__ = "fact_daily_sales"
    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(String, ForeignKey("datasets.dataset_id"), nullable=True, index=True)
    date = Column(Date, nullable=False, index=True)
    store_id = Column(String, ForeignKey("dim_stores.store_id"), index=True)
    sku_id = Column(String, ForeignKey("dim_products.sku_id"), index=True)
    stock_on_hand_start = Column(Integer)
    units_sold = Column(Integer)
    units_demanded_est = Column(Integer)      # Oracle — jangan jadi input model
    stock_on_hand_end = Column(Integer)
    promo_flag = Column(Boolean)
    stockout_flag = Column(Boolean)
    unit_cost_rp = Column(Float)
    unit_price_rp = Column(Float)
    demand_profile = Column(String)           # Oracle
    revenue_rp = Column(Float)
    cash_locked_in_stock_rp = Column(Float)   # Oracle


class PurchaseOrder(Base):
    __tablename__ = "fact_purchase_orders"
    po_id = Column(String, primary_key=True)
    dataset_id = Column(String, ForeignKey("datasets.dataset_id"), nullable=True, index=True)
    store_id = Column(String, ForeignKey("dim_stores.store_id"))
    sku_id = Column(String, ForeignKey("dim_products.sku_id"))
    supplier_id = Column(String, ForeignKey("dim_suppliers.supplier_id"))
    order_date = Column(Date)
    order_qty_units = Column(Integer)
    promised_lead_time_days = Column(Integer)
    actual_delivery_date = Column(Date)
    actual_lead_time_days = Column(Integer)
    delay_days = Column(Integer)


# ============================================
# TABEL PRODUK BARU (fitur RestockIQ sendiri)
# ============================================

class Dataset(Base):
    __tablename__ = "datasets"
    dataset_id = Column(String, primary_key=True)
    source_type = Column(String, nullable=False)   # "demo" atau "upload"
    data_hash = Column(String)
    readiness_status = Column(String, default="pending")  # pending/valid/invalid
    created_at = Column(DateTime)


class DecisionRun(Base):
    __tablename__ = "decision_runs"
    run_id = Column(String, primary_key=True)
    dataset_id = Column(String, ForeignKey("datasets.dataset_id"))
    store_id = Column(String, nullable=False)
    decision_date = Column(Date, nullable=False)
    budget_rp = Column(Float, nullable=False)
    policy_preset = Column(String, default="balanced")
    constraints_json = Column(JSON)
    model_version = Column(String)
    data_hash = Column(String)
    status = Column(String, default="queued")   # queued/running/completed/failed
    runtime_ms = Column(Integer)
    created_at = Column(DateTime)


class Recommendation(Base):
    __tablename__ = "recommendations"
    recommendation_id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("decision_runs.run_id"), index=True)
    sku_id = Column(String, nullable=False)
    original_qty = Column(Integer)
    adjusted_qty = Column(Integer, nullable=True)
    status = Column(String, default="belum_diputuskan")  # belum_diputuskan/disetujui/diedit/ditolak
    before_metrics_json = Column(JSON)
    after_metrics_json = Column(JSON)
    explanation_json = Column(JSON)