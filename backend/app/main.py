from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import ALLOWED_ORIGINS
from app.api.routes import datasets
from app.api.routes import datasets, decision_runs
from app.api.routes import datasets, decision_runs, recommendations, export

app = FastAPI(title="RestockIQ API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v2"
app.include_router(datasets.router, prefix=API_PREFIX)
app.include_router(decision_runs.router, prefix=API_PREFIX)
app.include_router(recommendations.router, prefix=API_PREFIX)
app.include_router(export.router, prefix=API_PREFIX)


@app.get("/health")
def health_check():
    return {"status": "ok"}