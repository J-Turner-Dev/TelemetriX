import argparse
from app.db import get_conn
from ingest.simulator import simulate
from ingest.faults import inject_faults
from ingest.store import create_flight, write_measurements, write_faults

def main():
    ap = argparse.ArgumentParser(description="Generate and store one simulated flight")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--faults", type=int, default=2)
    args = ap.parse_args()

    df = simulate(args.seed)
    faults = inject_faults(df, args.seed, args.faults)

    with get_conn() as conn:
        flight_id, started = create_flight(
            conn, "simulated", f"sim-seed-{args.seed}", f"{len(faults)} injected faults")
        n = write_measurements(conn, flight_id, started, df)
        write_faults(conn, flight_id, started, faults)
    print(f"Flight {flight_id}: {n} readings stored")
    for f in faults:
        print(f"  {f['kind']:9s} {f['sensor']:17s} T+{f['start_t']:.1f}s to T+{f['end_t']:.1f}s")

if __name__ == "__main__":
    main()