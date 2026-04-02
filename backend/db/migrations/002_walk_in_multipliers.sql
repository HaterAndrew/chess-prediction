-- 002_walk_in_multipliers.sql — Walk-in entry tracking
--
-- Adds walk-in multiplier table (standings vs pre-reg delta) and
-- extends predictions with total entry estimates.

CREATE TABLE IF NOT EXISTS walk_in_multipliers (
    id SERIAL PRIMARY KEY,
    family VARCHAR(255) NOT NULL,
    year INT NOT NULL,
    prereg_count INT,
    standings_count INT,
    walk_in_ratio DECIMAL,
    tournament_type VARCHAR(20),
    UNIQUE (family, year)
);

ALTER TABLE predictions
    ADD COLUMN IF NOT EXISTS walkin_multiplier DECIMAL,
    ADD COLUMN IF NOT EXISTS predicted_total_entries DECIMAL,
    ADD COLUMN IF NOT EXISTS total_ci_lower DECIMAL,
    ADD COLUMN IF NOT EXISTS total_ci_upper DECIMAL;
