from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import datasets, decision_runs, recommendations, export
from app.core.config import ALLOWED_ORIGINS
from app.db.session import engine
from app.ml.artifact_store import ArtifactError, load_model_artifacts

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


@app.get("/health/live")
def liveness_check():
    return {"status": "alive"}


@app.get("/health/ready")
def readiness_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        artifacts = load_model_artifacts()
    except (SQLAlchemyError, ArtifactError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"RestockIQ belum siap: {exc}",
        ) from exc

    return {
        "status": "ready",
        "model_version": artifacts.version,
        "training_cutoff": artifacts.training_cutoff,
    }
