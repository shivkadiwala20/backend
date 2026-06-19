-- SQLite dialect — German Road Accident Platform
-- PRAGMA settings are applied per-connection in database.py
-- Uses INTEGER 1/0 for booleans, CHECK constraints for enums

-- ─────────────────────────────────────────────────────────────────────────────
-- DATA SOURCES  (provenance table — created FIRST because accidents reference it)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS data_sources (
    source_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,           -- e.g. 'Unfallatlas 2023'
    origin_url     TEXT,
    file_name      TEXT,
    license        TEXT,                    -- e.g. 'dl-de/by-2-0'
    retrieved_at   TEXT DEFAULT (datetime('now')),
    records_loaded INTEGER,
    run_status     TEXT DEFAULT 'pending'
                   CHECK(run_status IN ('pending','running','success','error')),
    error_notes    TEXT
);

-- ─────────────────────────────────────────────────────────────────────────────
-- LOCATIONS  (regions: states, districts, municipalities)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS locations (
    location_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ags           TEXT NOT NULL UNIQUE,     -- zero-padded: 2=state, 5=district, 8=municipality
    name          TEXT NOT NULL,
    location_type TEXT NOT NULL
                  CHECK(location_type IN ('state','district','municipality')),
    parent_ags    TEXT,                     -- AGS of parent region
    population    INTEGER,
    area_km2      REAL,
    created_at    TEXT DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- ACCIDENT EVENTS  (core fact table — no participant flags here — 3NF design)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accident_events (
    event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id      TEXT,                    -- UIDENTSTLAE from CSV
    year           INTEGER NOT NULL,
    month          INTEGER CHECK(month BETWEEN 1 AND 12),
    hour           INTEGER CHECK(hour BETWEEN 0 AND 23),
    weekday        INTEGER CHECK(weekday BETWEEN 1 AND 7),  -- 1=Sunday, 7=Saturday
    severity       INTEGER CHECK(severity IN (1,2,3)),      -- 1=fatal,2=severe,3=light
    accident_type  INTEGER,                 -- UART
    road_type      INTEGER,                 -- UTYP1
    light_cond     INTEGER CHECK(light_cond IN (0,1,2)),    -- 0=day,1=dusk,2=dark
    lon            REAL,
    lat            REAL,
    location_id    INTEGER REFERENCES locations(location_id),
    ags            TEXT,                    -- denormalised 8-digit AGS for fast LIKE queries
    data_source_id INTEGER REFERENCES data_sources(source_id),
    UNIQUE(source_id, year)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- ACCIDENT PARTICIPANTS  (normalised — one row per participant type per event)
-- WHY: allows "accidents involving BOTH bicycle AND pedestrian" queries
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accident_participants (
    participant_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id         INTEGER NOT NULL REFERENCES accident_events(event_id) ON DELETE CASCADE,
    participant_type TEXT NOT NULL
                     CHECK(participant_type IN ('bicycle','car','pedestrian','motorcycle','truck','other'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_unique
    ON accident_participants(event_id, participant_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- STATISTICAL INDICATORS  (metadata for cross-source indicators)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS statistical_indicators (
    indicator_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,     -- e.g. 'population', 'accident_rate_per_10k'
    label         TEXT NOT NULL,
    unit          TEXT,
    source_system TEXT                      -- e.g. 'Destatis', 'GENESIS', 'Unfallatlas-Fallback'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- STATISTICAL VALUES  (cross-source indicator values per location per year)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS statistical_values (
    value_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id  INTEGER REFERENCES locations(location_id),
    indicator_id INTEGER REFERENCES statistical_indicators(indicator_id),
    year         INTEGER NOT NULL,
    value        REAL,
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
