"""Inject labeled faults into a simulated flight. Returns ground-truth records."""
import numpy as np
import pandas as pd
from ingest.simulator import SENSORS, NOISE_STD, STAGING_T

FAULT_KINDS = ["spike", "dropout", "flatline", "drift", "offset"]

def inject_faults(df: pd.DataFrame, seed: int, n_faults: int = 2, dt: float = 0.1):
    """Modify df in place (NaN marks dropped samples). Returns list of fault dicts."""
    rng = np.random.default_rng(seed + 10_000)
    faults, used = [], []
    attempts = 0
    while len(faults) < n_faults and attempts < 100:
        attempts += 1
        kind = str(rng.choice(FAULT_KINDS))
        sensor = str(rng.choice(SENSORS))
        length_s = {"spike": 0.3, "dropout": rng.uniform(2, 5), "flatline": rng.uniform(5, 10),
                    "drift": rng.uniform(20, 40), "offset": rng.uniform(10, 20)}[kind]
        length = max(1, int(length_s / dt))
        start = int(rng.uniform(10.0, df["t"].iloc[-1] - 50.0) / dt)
        end = start + length
        t0, t1 = start * dt, end * dt
        if t0 < STAGING_T + 5 and t1 > STAGING_T - 5:    # keep clear of staging
            continue
        if any(not (end + 100 < s or start > e + 100) for s, e in used):    #keep faults apart
            continue
        used.append((start, end))
        std = NOISE_STD[sensor]
        ci = df.columns.get_loc(sensor)
        params = {}
        if kind == "spike":
            mag = float(rng.choice([-1, 1]) * 15 * std)
            df.iloc[start:end, ci] += mag; params["magnitude"] = mag
        elif kind == "dropout":
            df.iloc[start:end, ci] = np.NaN
        elif kind == "flatline":
            held = float(df.iloc[start, ci]); df.iloc[start:end, ci] = held; params["held_value"] = held
        elif kind == "drift":
            peak = float(rng.choice([-1, 1]) * 30 * std)
            df.iloc[start:end, ci] += np.linspace(0, peak, length); params["peak"] = peak
        elif kind == "offset":
            mag = float(rng.choice([-1, 1]) * 20 * std)
            df.iloc[start:end, ci] += mag; params["magnitude"] = mag
        faults.append(dict(sensor=sensor, kind=kind, start_t=t0, end_t=t1, params=params))
    return faults