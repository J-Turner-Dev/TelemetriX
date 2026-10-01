CREATE TABLE flights (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL CHECK (source IN ('simulated', 'live', 'video')),
    name        TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    notes       TEXT
);

CREATE TABLE sensors (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    unit            TEXT NOT NULL,
    expected_min    DOUBLE PRECISION,
    expected_max    DOUBLE PRECISION,
    noise_std       DOUBLE PRECISION
);

CREATE TABLE measurements (
    flight_id   INTEGER NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    sensor_id   INTEGER NOT NULL REFERENCES sensors(id),
    ts          TIMESTAMPTZ NOT NULL,
    value      DOUBLE PRECISION,
    PRIMARY KEY (flight_id, sensor_id, ts)
);

CREATE TABLE anomalies (
    id  SERIAL PRIMARY KEY,
    flight_id           INTEGER NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    sensor_id           INTEGER REFERENCES sensors(id),
    ts                  TIMESTAMPTZ NOT NULL,
    kind                TEXT NOT NULL,
    score               DOUBLE PRECISION,
    reason              TEXT,
    detector_version    TEXT
);

CREATE INDEX anomalies_flights_ts ON anomalies (flight_id, ts);

CREATE TABLE injected_faults (
    id          SERIAL PRIMARY KEY,
    flight_id   INTEGER NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    sensor_id   INTEGER NOT NULL REFERENCES sensors(id),
    start_ts    TIMESTAMPTZ NOT NULL,
    end_ts      TIMESTAMPTZ NOT NULL,
    kind        TEXT NOT NULL,
    params      JSONB
);

CREATE TABLE evaluation_runs (
    id          SERIAL PRIMARY KEY,
    run_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    n_flights   INTEGER NOT NULL,
    seed        INTEGER NOT NULL,
    results     JSONB NOT NULL
);

INSERT INTO sensors (name, unit, expected_min, expected_max, noise_std) VALUES
    ('altitude',            'm',        0,      400000,     5.0),
    ('velocity',            'm/s',      0,      8000,       1.0),
    ('acceleration',        'm/s^2',    20,     60,         0.3),
    ('chamber_pressure',    'bar',      0,      300,        1.5),
    ('tank_pressure',       'bar',      0,      10,         0.05),
    ('engine_temp',         'K',        250,    3800,       8.0);