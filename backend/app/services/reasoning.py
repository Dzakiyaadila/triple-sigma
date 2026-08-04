"""
Generator teks penjelasan (reasoning) berbasis rule, BUKAN model AI/NLP.
Backend menerjemahkan angka mentah (reason_codes, metrik risiko) dari modul ML
jadi kalimat yang bisa dibaca pemilik toko. Ini tanggung jawab backend,
bukan Della — lihat PRD bagian 8.
"""
import hashlib


def _pick(options: list[str], seed: str) -> str:
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(options)
    return options[idx]


SHORT_TEMPLATES = {
    frozenset(["risiko_stockout_tinggi", "supplier_andal"]):
        "Risiko kehabisan stok tinggi. Supplier cukup bisa diandalkan.",
    frozenset(["risiko_stockout_tinggi", "supplier_kurang_andal"]):
        "Risiko kehabisan stok tinggi, tapi supplier sering telat — sebaiknya pesan lebih awal.",
    frozenset(["data_historis_kurang"]):
        "Data histori penjualan masih terbatas, sistem memakai perkiraan kategori.",
}


def generate_reasoning(rec: dict) -> dict:
    codes = frozenset(rec.get("reason_codes", []))
    qty = rec["recommended_qty"]
    effective = rec["effective_inventory"]
    q90 = rec["forecast_q90"]
    lead = rec["supplier_p90_lead_time_days"]
    sku_id = rec["sku_id"]

    reasoning_short = SHORT_TEMPLATES.get(codes)
    if not reasoning_short:
        if "risiko_stockout_tinggi" in codes:
            reasoning_short = "Risiko kehabisan stok cukup tinggi, prioritaskan restock."
        elif "data_historis_kurang" in codes:
            reasoning_short = "Data histori penjualan masih terbatas untuk SKU ini."
        else:
            reasoning_short = "Permintaan cukup stabil, restock dalam jumlah wajar."

    more_options = [
        f"Dengan posisi stok efektif {effective} unit dan perkiraan permintaan sampai {q90} unit, "
        f"{qty} unit ini menutup kebutuhan sekaligus menyisakan sedikit cadangan untuk waktu "
        f"pengiriman sekitar {lead} hari.",
        f"Angka {qty} unit dipilih supaya total stok mendekati batas atas perkiraan permintaan "
        f"({q90} unit), tanpa menyisakan kelebihan yang menahan modal terlalu lama.",
    ]
    not_more_options = [
        "Menambah lebih banyak lagi hanya sedikit menurunkan risiko kehabisan, sementara modal "
        "yang tertahan naik lebih cepat daripada manfaatnya.",
        "Di atas jumlah ini, tambahan margin yang terselamatkan tidak sebanding dengan modal "
        "kerja tambahan yang ikut tertahan.",
    ]

    return {
        "reasoning_short": reasoning_short,
        "reason_more": _pick(more_options, sku_id + "more"),
        "reason_not_more": _pick(not_more_options, sku_id + "notmore"),
    }