"""
Cache in-memory sederhana untuk menyimpan hasil plan per run.
Untuk MVP ini cukup, karena server tidak akan restart di tengah demo.
Kalau nanti butuh persist lintas restart, tinggal ganti ke query dari DB.
"""
plans_cache: dict[str, dict] = {}