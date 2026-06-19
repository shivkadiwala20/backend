-- PostgreSQL dialect — German Road Accident Platform
-- Run automatically by init_db() on first startup.
-- All tables use IF NOT EXISTS so re-running is safe.

-- ─────────────────────────────────────────────────────────────────────────────
-- DATA SOURCES  (provenance — created FIRST because accident_events references it)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS data_sources (
    source_id      SERIAL PRIMARY KEY,
    name           TEXT        NOT NULL,
    origin_url     TEXT,
    file_name      TEXT,
    license        TEXT,                    -- e.g. 'dl-de/by-2-0'
    retrieved_at   TIMESTAMP   DEFAULT NOW(),
    records_loaded INTEGER,
    run_status     TEXT        DEFAULT 'pending'
                               CHECK(run_status IN ('pending','running','success','error')),
    error_notes    TEXT
);

-- ─────────────────────────────────────────────────────────────────────────────
-- LOCATIONS  (states, districts, municipalities — zero-padded AGS key)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS locations (
    location_id   SERIAL PRIMARY KEY,
    ags           TEXT        NOT NULL UNIQUE,   -- 2=state, 5=district, 8=municipality
    name          TEXT        NOT NULL,
    location_type TEXT        NOT NULL
                              CHECK(location_type IN ('state','district','municipality')),
    parent_ags    TEXT,
    population    INTEGER,
    area_km2      DOUBLE PRECISION,
    created_at    TIMESTAMP   DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- ACCIDENT EVENTS  (core fact table — participant types are normalised out, 3NF)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accident_events (
    event_id       SERIAL PRIMARY KEY,
    source_id      TEXT,                         -- UIDENTSTLAE from CSV
    year           INTEGER     NOT NULL,
    month          INTEGER     CHECK(month    BETWEEN 1 AND 12),
    hour           INTEGER     CHECK(hour     BETWEEN 0 AND 23),
    weekday        INTEGER     CHECK(weekday  BETWEEN 1 AND 7),   -- 1=Sunday…7=Saturday
    severity       INTEGER     CHECK(severity IN (1,2,3)),        -- 1=fatal,2=severe,3=light
    accident_type  INTEGER,                       -- UART
    road_type      INTEGER,                       -- UTYP1
    light_cond     INTEGER     CHECK(light_cond IN (0,1,2)),      -- 0=day,1=dusk,2=dark
    lon            DOUBLE PRECISION,
    lat            DOUBLE PRECISION,
    location_id    INTEGER     REFERENCES locations(location_id),
    ags            TEXT,                          -- denormalised 8-digit AGS for fast LIKE queries
    data_source_id INTEGER     REFERENCES data_sources(source_id),
    UNIQUE(source_id, year)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- ACCIDENT PARTICIPANTS  (normalised — one row per participant type per event)
-- WHY: enables "accidents involving BOTH bicycle AND pedestrian" queries
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accident_participants (
    participant_id   SERIAL PRIMARY KEY,
    event_id         INTEGER NOT NULL REFERENCES accident_events(event_id) ON DELETE CASCADE,
    participant_type TEXT    NOT NULL
                             CHECK(participant_type IN
                                   ('bicycle','car','pedestrian','motorcycle','truck','other'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_unique
    ON accident_participants(event_id, participant_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- STATISTICAL INDICATORS  (metadata for cross-source indicators)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS statistical_indicators (
    indicator_id  SERIAL PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,           -- e.g. 'population', 'accident_rate_per_10k'
    label         TEXT NOT NULL,
    unit          TEXT,                           -- e.g. 'persons', 'accidents per 10,000'
    source_system TEXT                            -- e.g. 'Destatis', 'GENESIS'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- STATISTICAL VALUES  (cross-source values per location per year)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS statistical_values (
    value_id     SERIAL PRIMARY KEY,
    location_id  INTEGER REFERENCES locations(location_id),
    indicator_id INTEGER REFERENCES statistical_indicators(indicator_id),
    year         INTEGER NOT NULL,
    value        DOUBLE PRECISION,
    UNIQUE(location_id, indicator_id, year)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- PERFORMANCE INDEXES
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_events_year        ON accident_events(year);
CREATE INDEX IF NOT EXISTS idx_events_ags         ON accident_events(ags);
CREATE INDEX IF NOT EXISTS idx_events_location    ON accident_events(location_id);
CREATE INDEX IF NOT EXISTS idx_events_severity    ON accident_events(severity);
CREATE INDEX IF NOT EXISTS idx_events_datasource  ON accident_events(data_source_id);
CREATE INDEX IF NOT EXISTS idx_participants_type  ON accident_participants(participant_type);
CREATE INDEX IF NOT EXISTS idx_participants_event ON accident_participants(event_id);
CREATE INDEX IF NOT EXISTS idx_locations_type     ON locations(location_type);
CREATE INDEX IF NOT EXISTS idx_locations_ags      ON locations(ags);
CREATE INDEX IF NOT EXISTS idx_stat_values        ON statistical_values(location_id, indicator_id, year);
