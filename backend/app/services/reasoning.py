"""Deterministic merchant-facing explanation templates.

The ML layer owns numbers and reason codes. This service only translates the
validated analytical output into readable Indonesian; it does not invent new
risk metrics or model decisions.
"""
import hashlib


def _pick(options: list[str], seed: str) -> str:
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(options)
    return options[idx]


def generate_reasoning(rec: dict) -> dict:
    codes = set(rec.get("reason_codes", []))
    qty = int(rec["recommended_qty"])
    effective = float(rec["effective_inventory"])
    q50 = float(rec["forecast_q50"])
    q90 = float(rec["forecast_q90"])
    lead = float(rec["supplier_p90_lead_time_days"])
    sku_id = rec["sku_id"]

    if "data_historis_kurang" in codes:
        reasoning_short = (
            "Data histori masih terbatas; rekomendasi memakai estimasi yang "
            "lebih konservatif."
        )
    elif "risiko_stockout_tinggi" in codes and "supplier_andal" in codes:
        reasoning_short = (
            "Risiko kehabisan stok tinggi dan supplier relatif dapat diandalkan."
        )
    elif "risiko_stockout_tinggi" in codes:
        reasoning_short = (
            "Risiko kehabisan stok tinggi, sementara ketepatan supplier terbatas."
        )
    elif "supplier_kurang_andal" in codes:
        reasoning_short = (
            "Stok masih relatif aman, tetapi ketidakpastian supplier tetap diperhitungkan."
        )
    else:
        reasoning_short = "Posisi stok dan risiko saat ini relatif terkendali."

    if qty <= 0:
        more_options = [
            f"Stok efektif sekitar {effective:.1f} unit sudah memadai terhadap "
            f"perkiraan permintaan median {q50:.1f} unit, sehingga optimizer tidak "
            "mengalokasikan pembelian tambahan pada budget ini.",
            f"Dengan stok efektif {effective:.1f} unit dan rentang permintaan hingga "
            f"Q90 {q90:.1f} unit, tambahan order belum memberi manfaat bersih yang "
            "cukup dibanding risiko modal tertahan.",
        ]
        not_more_options = [
            "Tambahan pembelian saat ini menaikkan risiko modal kerja lebih cepat "
            "daripada margin yang diperkirakan dapat diselamatkan.",
            "Budget lebih bernilai bila dialokasikan ke SKU lain dengan penurunan "
            "risiko yang lebih besar per Rupiah.",
        ]
    else:
        more_options = [
            f"Optimizer memilih {qty} unit setelah memperhitungkan stok efektif "
            f"{effective:.1f} unit, permintaan Q50 {q50:.1f} hingga Q90 {q90:.1f}, "
            f"dan P90 lead time supplier {lead:.1f} hari.",
            f"Jumlah {qty} unit adalah titik trade-off terpilih antara margin yang "
            "berisiko hilang dan modal kerja tambahan, setelah ketidakpastian "
            f"kedatangan supplier sekitar {lead:.1f} hari diperhitungkan.",
        ]
        not_more_options = [
            "Di atas jumlah ini, tambahan penurunan LMAR tidak lagi sebanding "
            "dengan kenaikan WCAR pada policy yang dipilih.",
            "Quantity yang lebih besar kalah pada objective budget karena manfaat "
            "marginalnya lebih kecil dibanding tambahan modal yang harus dialokasikan.",
        ]

    return {
        "reasoning_short": reasoning_short,
        "reason_more": _pick(more_options, sku_id + "more"),
        "reason_not_more": _pick(not_more_options, sku_id + "notmore"),
    }
