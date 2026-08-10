"""Optional process-local plan cache.

PostgreSQL is the R8 source of truth. Routes rebuild plans from persisted
DecisionRun and Recommendation rows, so this cache may be empty or stale after
a restart without affecting correctness.
"""
plans_cache: dict[str, dict] = {}
