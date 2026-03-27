"""
Celery application and beat schedule.

One automated job: canonical scrape at 2015 ET daily (post CCA day-close).
All other scrapes are on-demand via the dashboard "Refresh" button.
"""

from celery import Celery
from celery.schedules import crontab

from backend.config import settings

app = Celery(
    "chess_predictor",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

app.conf.update(
    timezone=settings.cca_timezone,
    enable_utc=True,
)

app.conf.beat_schedule = {
    # ── Canonical daily scrape: 2015 ET, post CCA day-close ──
    "canonical-daily-scrape": {
        "task": "backend.workers.tasks.scrape_all_tournaments",
        "schedule": crontab(
            hour=settings.canonical_scrape_hour,
            minute=settings.canonical_scrape_minute,
        ),
        "kwargs": {"canonical": True},
    },
}
