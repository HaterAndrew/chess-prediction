"""
FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import tournaments, entries, predictions, alerts, scrape
from backend.config import settings

app = FastAPI(
    title="Chess Entry Predictor",
    description="SaaS dashboard for chess tournament directors — live registration tracking and predictive modeling.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server; restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(tournaments.router, prefix="/api/v1/tournaments", tags=["tournaments"])
app.include_router(entries.router, prefix="/api/v1/entries", tags=["entries"])
app.include_router(predictions.router, prefix="/api/v1/predictions", tags=["predictions"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])
app.include_router(scrape.router, prefix="/api/v1/scrape", tags=["scrape"])


@app.get("/health")
def health_check():
    return {"status": "ok", "env": settings.app_env}
