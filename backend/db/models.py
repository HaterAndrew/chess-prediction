"""
SQLAlchemy ORM models — mirrors the schema defined in migrations/001_init.sql.
"""

from datetime import datetime
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey,
    Integer, Numeric, String, Text, func
)
from sqlalchemy import JSON
from sqlalchemy.orm import relationship

from backend.db.session import Base


class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    location = Column(String(255))
    prize_fund = Column(Numeric)
    # [{name, fee_tiers: [{deadline, price}]}]
    sections = Column(JSON)
    # competing events, hotel info, confirmed GMs, registration URL
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime, server_default=func.now())
    # Updated on every scrape (canonical or on-demand) — powers "as of" display
    last_scraped_at = Column(DateTime)
    last_entry_count = Column(Integer)

    entries = relationship("Entry", back_populates="tournament")
    predictions = relationship("Prediction", back_populates="tournament")
    alerts = relationship("Alert", back_populates="tournament")


class Entry(Base):
    __tablename__ = "entries"

    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    player_name = Column(String(255))
    section = Column(String(100))
    registered_at = Column(DateTime)
    scraped_at = Column(DateTime, server_default=func.now())
    # Which CCA-day this entry belongs to.  CCA resets at 2000 ET,
    # so a scrape at 2015 ET on Mar 26 → cca_day_date = Mar 26.
    # A scrape at 1945 ET on Mar 26 → cca_day_date = Mar 25 (day not yet closed).
    cca_day_date = Column(Date)
    is_canonical = Column(Boolean, default=False)  # True = post-close 2015 ET pull

    tournament = relationship("Tournament", back_populates="entries")


class DailySnapshot(Base):
    """Aggregate entry count per CCA-day per tournament.

    One row per tournament per CCA-day.  The canonical scrape (2015 ET)
    populates this; intra-day scrapes do not.
    """
    __tablename__ = "daily_snapshots"

    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    cca_day_date = Column(Date, nullable=False)
    entry_count = Column(Integer, nullable=False)
    scraped_at = Column(DateTime, server_default=func.now())

    tournament = relationship("Tournament")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    predicted_at = Column(DateTime, server_default=func.now())
    model_version = Column(String(50))
    prediction_date = Column(Date)     # what future date this prediction is FOR
    predicted_entries = Column(Numeric)
    ci_lower = Column(Numeric)         # 90% credible interval lower bound
    ci_upper = Column(Numeric)         # 90% credible interval upper bound
    parameters = Column(JSON)         # fitted model params snapshot
    # Walk-in adjusted predictions (pre-reg * walk-in multiplier)
    walkin_multiplier = Column(Numeric)
    predicted_total_entries = Column(Numeric)
    total_ci_lower = Column(Numeric)
    total_ci_upper = Column(Numeric)

    tournament = relationship("Tournament", back_populates="predictions")


class WalkInMultiplier(Base):
    """Historical walk-in ratios: actual entries (standings) / pre-reg entries."""
    __tablename__ = "walk_in_multipliers"

    id = Column(Integer, primary_key=True)
    family = Column(String(255), nullable=False)
    year = Column(Integer, nullable=False)
    prereg_count = Column(Integer)
    standings_count = Column(Integer)
    walk_in_ratio = Column(Numeric)
    tournament_type = Column(String(20))  # 'open' or 'class'


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    # 'below_threshold' | 'above_threshold' | 'anomaly'
    alert_type = Column(String(50))
    threshold_pct = Column(Numeric)
    actual_value = Column(Numeric)
    expected_value = Column(Numeric)
    triggered_at = Column(DateTime, server_default=func.now())
    acknowledged = Column(Boolean, default=False)

    tournament = relationship("Tournament", back_populates="alerts")
