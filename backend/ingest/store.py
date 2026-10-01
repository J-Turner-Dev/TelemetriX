from datetime import datetime, timedelta, timezone
from psycopg.types.json import Jsonb

def sensor_ids(conn) -> dict:
    return dict(conn.execute("SELECT name, id FROM sensors").fetchall())

def create_flight(conn, source: str, name: str, notes: str | None = None):
    started = datetime.now(timezone.utc)
    row = conn.execute(
        "INSERT INTO flights (source, name, started_at, notes) VALUES (%s, %s, %s, %s) "
        "RETURNING id, started_at", (source, name, started, notes)).fetchone()
    return row[0], row[1]

def write_measurements(conn, flight_id: int, started_at, df) -> int:
    """Bulk-insert readings. NaN (dropped) samples are skipped, leaving real gaps."""
    ids = sensor_ids(conn)
    long = df.melt(id_vars="t", var_name="sensor", value_name="value").dropna(subset=["value"])
    with conn.cursor() as cur:
        with cur.copy("COPY measurements (flight_id, sensor_id, ts, value) FROM STDIN") as copy:
            for t, sensor, value in long.itertuples(index=False):
                copy.write_row((flight_id, ids[sensor],
                                started_at + timedelta(seconds=round(float(t), 1)), float(value)))
    return len(long)

def write_faults(conn, flight_id: int, started_at, faults: list):
    ids = sensor_ids(conn)
    for f in faults:
        conn.execute(
            "INSERT INTO injected_faults (flight_id, sensor_id, start_ts, end_ts, kind, params) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (flight_id, ids[f["sensor"]],
             started_at + timedelta(seconds=f["start_t"]),
             started_at + timedelta(seconds=f["end_t"]),
             f["kind"], Jsonb(f["params"])))