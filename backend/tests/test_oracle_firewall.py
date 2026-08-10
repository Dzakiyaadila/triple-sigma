from app.db.models import Product, DailySales

ORACLE_COLUMNS = {
    "units_demanded_est",
    "demand_profile",
    "avg_daily_demand_per_store",
    "cash_locked_in_stock_rp",
}


def test_product_dict_sent_to_ml_excludes_oracle_columns():
    """
    Memastikan dict yang disiapkan buat dikirim ke generate_restock_plan()
    tidak pernah menyertakan kolom Oracle. Cek langsung ke cara
    decision_run_service.py menyusun product_dicts.
    """
    from app.services.decision_run_service import run_decision
    import inspect

    source = inspect.getsource(run_decision)
    for col in ORACLE_COLUMNS:
        assert col not in source, (
            f"Kolom Oracle '{col}' terdeteksi di kode yang menyiapkan data untuk model. "
            "Ini pelanggaran data leakage."
        )


def test_oracle_columns_exist_only_for_evaluation():
    """Sekadar dokumentasi hidup: kolom ini memang ada di DB, tapi ditandai jelas."""
    product_columns = {c.name for c in Product.__table__.columns}
    sales_columns = {c.name for c in DailySales.__table__.columns}

    assert "demand_profile" in product_columns
    assert "units_demanded_est" in sales_columns