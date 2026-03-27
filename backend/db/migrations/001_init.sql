-- 001_init.sql — Core schema with CCA-day-aware entry tracking
--
-- CCA resets daily at 2000 ET.  Canonical scrape at 2015 ET.
-- cca_day_date tells us which CCA-day a row belongs to.
-- daily_snapshots stores one count per tournament per CCA-day
-- for clean year-over-year comparisons.

CREATE TABLE IF NOT EXISTS tournaments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    start_date DATE,
    end_date DATE,
    location VARCHAR(255),
    prize_fund DECIMAL,
    sections JSONB,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    last_scraped_at TIMESTAMP,          -- any scrape (canonical or on-demand)
    last_entry_count INT                -- powers "249 entries as of Mar 27, 3:42 PM ET"
);

CREATE TABLE IF NOT EXISTS entries (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES tournaments(id),
    player_name VARCHAR(255),
    section VARCHAR(100),
    registered_at TIMESTAMP,
    scraped_at TIMESTAMP DEFAULT NOW(),
    cca_day_date DATE,
    is_canonical BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_entries_tournament_cca_day
    ON entries (tournament_id, cca_day_date);

CREATE INDEX idx_entries_canonical
    ON entries (tournament_id, is_canonical)
    WHERE is_canonical = TRUE;

CREATE TABLE IF NOT EXISTS daily_snapshots (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES tournaments(id),
    cca_day_date DATE NOT NULL,
    entry_count INT NOT NULL,
    scraped_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (tournament_id, cca_day_date)
);

CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES tournaments(id),
    predicted_at TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    prediction_date DATE,
    predicted_entries DECIMAL,
    ci_lower DECIMAL,
    ci_upper DECIMAL,
    parameters JSONB
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES tournaments(id),
    alert_type VARCHAR(50),
    threshold_pct DECIMAL,
    actual_value DECIMAL,
    expected_value DECIMAL,
    triggered_at TIMESTAMP DEFAULT NOW(),
    acknowledged BOOLEAN DEFAULT FALSE
);
