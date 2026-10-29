CREATE SEQUENCE IF NOT EXISTS laps_seq START 1;
CREATE SEQUENCE IF NOT EXISTS telemetry_seq START 1;
CREATE SEQUENCE IF NOT EXISTS weather_seq START 1;

CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(50) PRIMARY KEY,
    year INT NOT NULL,
    round_number INT NOT NULL,
    location VARCHAR(100) NOT NULL,
    session_type VARCHAR(20) NOT NULL,
    date_utc TIMESTAMP NOT NULL,
    event_name VARCHAR(100),
    total_laps INT,
    data_source VARCHAR(20),
    loaded_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS laps (
    lap_id INTEGER PRIMARY KEY DEFAULT nextval('laps_seq'),
    session_id VARCHAR(50) REFERENCES sessions(session_id),
    driver_number VARCHAR(10) NOT NULL,
    lap_number INT NOT NULL,
    lap_time_seconds DOUBLE PRECISION,
    sector1_seconds DOUBLE PRECISION,
    sector2_seconds DOUBLE PRECISION,
    sector3_seconds DOUBLE PRECISION,
    compound VARCHAR(20),
    tyre_life_laps INT,
    is_pit_out_lap BOOLEAN,
    is_pit_in_lap BOOLEAN,
    driver_code VARCHAR(5),
    team VARCHAR(50),
    stint INT,
    track_status VARCHAR(10),
    speed_trap_kmh DOUBLE PRECISION,
    is_accurate BOOLEAN,
    session_time_seconds DOUBLE PRECISION,
    position INT,
    UNIQUE (session_id, driver_number, lap_number)
);

CREATE TABLE IF NOT EXISTS telemetry_samples (
    sample_id BIGINT PRIMARY KEY DEFAULT nextval('telemetry_seq'),
    lap_id INT REFERENCES laps(lap_id),
    timestamp_utc TIMESTAMP NOT NULL,
    distance_meters DOUBLE PRECISION NOT NULL,
    speed_kmh DOUBLE PRECISION,
    throttle_pct DOUBLE PRECISION,
    brake_active BOOLEAN,
    drs_status INT,
    gear INT
);

CREATE TABLE IF NOT EXISTS weather_samples (
    weather_id BIGINT PRIMARY KEY DEFAULT nextval('weather_seq'),
    session_id VARCHAR(50) REFERENCES sessions(session_id),
    session_time_seconds DOUBLE PRECISION NOT NULL,
    air_temp_c DOUBLE PRECISION,
    track_temp_c DOUBLE PRECISION,
    humidity_pct DOUBLE PRECISION,
    pressure_hpa DOUBLE PRECISION,
    rainfall BOOLEAN,
    wind_speed_ms DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_laps_session ON laps (session_id, driver_code);
CREATE INDEX IF NOT EXISTS idx_telemetry_lap ON telemetry_samples (lap_id);
CREATE INDEX IF NOT EXISTS idx_weather_session ON weather_samples (session_id);
