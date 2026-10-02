"""Batch anomaly detectors for telemetry flights.

Input: DataFrame with column `t` (seconds) and one column per sensor. Dropped samples may be
missing rows or NaN. All detectors work on a uniform 10 Hz grid, NaN-aware.
"""
import numpy as np
import pandas as pd
from ingest.simulator import G0, R_EARTH, NOISE_STD, SENSORS, STAGING_T

DT = 0.1
DETECTOR_VERSION = "v1"

# Known, expected events that must not be flagged (liftoff ramp-up and stage separation)
KNOWN_EVENT_WINDOWS = [(0.0, 6.0), (STAGING_T - 4.0, STAGING_T + 6.0)]

def to_grid(df: pd.DataFrame) -> pd.DataFrame:
    idx = np.rint(df["t"].to_numpy() / DT).astype(int)
    g = df.drop(columns="t").set_index(idx)
    g = g[~g.index.duplicated()]
    return g.reindex(range(int(idx.max()) + 1))

def _mask(n: int) -> np.ndarray:
    m = np.zeros(n, dtype=bool)
    for a, b in KNOWN_EVENT_WINDOWS:
        m[int(a / DT):int(b / DT)] = True
    m[-11:] = True            # rolling windows are truncated at the end of the data
    return m

def spike_flags(x: pd.Series, noise: float, win: int = 21, thr: float = 6.0):
    """Rolling-median residual in units of the sensor's noise (a robust z-score)."""
    med = x.rolling(win, center=True, min_periods=win // 2).median()
    z = ((x - med) / noise).abs()
    return z > thr, z

def flatline_flags(x: pd.Series, noise: float, win: int = 10):
    """A live sensor always has noise; a window with ~zero variance means a stuck value."""
    sd = x.rolling(win, min_periods=win).std()
    flat = (sd < 0.05 * noise).astype(float)
    marked = flat[::-1].rolling(win, min_periods=1).max()[::-1] == 1.0   # cover whole window
    return marked, (0.05 * noise - sd).clip(lower=0) / (0.05 * noise)

def gap_flags(x: pd.Series):
    miss = x.isna()
    return miss, miss.astype(float)

def _gravity(alt: pd.Series) -> pd.Series:
    a = alt.interpolate(limit_area="inside").bfill().ffill().clip(lower=0)
    return G0 * (R_EARTH / (R_EARTH + a)) ** 2

def xcheck_vel_acc(g, noise, w: int = 10, thr: float = 6.0):
    """d(velocity)/dt must equal (accelerometer reading - gravity)."""
    expected = (g["acceleration"] - _gravity(g["altitude"])).rolling(
        2 * w + 1, center=True, min_periods=2 * w - 4).mean()
    measured = (g["velocity"].shift(-w) - g["velocity"].shift(w)) / (2 * w * DT)
    sigma = np.hypot(np.sqrt(2) * noise["velocity"] / (2 * w * DT),
                     noise["acceleration"] / np.sqrt(2 * w + 1))
    z = ((measured - expected) / sigma).abs()
    return z > thr, z

def xcheck_alt_vel(g, noise, w: int = 10, thr: float = 6.0):
    """d(altitude)/dt must equal velocity."""
    expected = g["velocity"].rolling(2 * w + 1, center=True, min_periods=2 * w - 4).mean()
    measured = (g["altitude"].shift(-w) - g["altitude"].shift(w)) / (2 * w * DT)
    sigma = np.hypot(np.sqrt(2) * noise["altitude"] / (2 * w * DT),
                     noise["velocity"] / np.sqrt(2 * w + 1))
    z = ((measured - expected) / sigma).abs()
    return z > thr, z

# Sensors with no physics partner; their healthy signal is flat or very slow.
INDEPENDENT_SENSORS = ["chamber_pressure", "tank_pressure", "engine_temp"]
# Drift via slope is only reliable where the healthy signal is flat (tank pressure oscillates slowly).
SLOPE_SENSORS = ["chamber_pressure", "engine_temp"]

def level_shift_flags(x: pd.Series, noise: float, win: int = 10, thr: float = 4.0):
    """Median of the next second vs the previous second: catches sudden offsets."""
    m = x.rolling(win, min_periods=win).median()
    post, pre = m.shift(-(win - 1)), m.shift(1)
    z = ((post - pre) / noise).abs()
    return z > thr, z

def slope_flags(x: pd.Series, noise: float, win: int = 100, thr: float = 8.0):
    """Linear-regression slope over 10 s (centered). Healthy flat sensors have ~zero slope."""
    n = len(x)
    t = pd.Series(np.arange(n) * DT, index=x.index)
    r = lambda y: y.rolling(win, center=True, min_periods=win).mean()
    slope = (r(t * x) - r(t) * r(x)) / (DT ** 2 * (win ** 2 - 1) / 12)
    sigma = noise / np.sqrt(DT ** 2 * win * (win ** 2 - 1) / 12)
    z = (slope / sigma).abs()
    flag = z > thr
    # slope windows are 10 s wide, so keep clear of the known events by 5 s on each side
    wide = pd.Series(False, index=x.index)
    for a, b in KNOWN_EVENT_WINDOWS:
        wide.iloc[int(max(a - 5, 0) / DT):int((b + 5) / DT)] = True
    return flag & ~wide, z

def to_events(flag: pd.Series, score: pd.Series, merge_gap: int = 10):
    """Merge runs of flagged samples (closer than merge_gap samples) into events."""
    idx = np.flatnonzero(flag.to_numpy())
    if len(idx) == 0:
        return []
    splits = np.flatnonzero(np.diff(idx) > merge_gap) + 1
    events = []
    for run in np.split(idx, splits):
        s = score.iloc[run].to_numpy()
        events.append(dict(start_t=run[0] * DT, end_t=(run[-1] + 1) * DT,
                           score=float(np.nanmax(s)) if np.isfinite(s).any() else 0.0))
    return events

def run_detectors(df: pd.DataFrame, noise: dict | None = None) -> list[dict]:
    noise = noise or NOISE_STD
    g = to_grid(df)
    mask = pd.Series(_mask(len(g)), index=g.index)
    out = []

    def add(flag, score, sensor, kind, reason, apply_mask=True):
        flag = flag & ~mask if apply_mask else flag
        for e in to_events(flag, score):
            out.append(dict(sensor=sensor, kind=kind, reason=reason, **e))
    
    for s in SENSORS:
        x = g[s]
        f, z = spike_flags(x, noise[s]);            add(f, z, s, "spike", f"{s}: reading far from local median")
        f, z = flatline_flags(x, noise[s]);         add(f, z, s, "flatline", f"{s}: value stuck (no noise)")
        f, z = gap_flags(x);                        add(f, z, s, "gap", f"{s}: missing samples", apply_mask=False)
    for s in INDEPENDENT_SENSORS:
        f, z = level_shift_flags(g[s], noise[s]);   add(f, z, s, "level_shift", f"{s}: sudden step in level")
    for s in SLOPE_SENSORS:
        f, z = slope_flags(g[s], noise[s]);         add(f, z, s, "drift", f"{s}: sustained slope on a flat signal")
    f, z = xcheck_vel_acc(g, noise);                add(f, z, None, "xcheck_vel_acc", "d(velocity)/dt disagrees with accelerometer minus gravity")
    f, z = xcheck_alt_vel(g, noise);                add(f, z, None, "xcheck_alt_vel", "d(altitude)/dt disagrees with velocity")
    return sorted(out, key=lambda e: e["start_t"])