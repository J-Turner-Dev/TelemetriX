"""Simplified 1-D vertical rocket ascent, sampled at 10 Hz."""
import numpy as np
import pandas as pd

G0 = 9.80665
R_EARTH = 6_371_000.0
SENSORS = ["altitude", "velocity", "acceleration",
           "chamber_pressure", "tank_pressure", "engine_temp"]
NOISE_STD = {"altitude": 5.0, "velocity": 1.0, "acceleration": 0.3,
             "chamber_pressure": 1.5, "tank_pressure": 0.05, "engine_temp": 8.0}

STAGING_T = 150.0 # seconds
CD_A = 3.0        # drag coefficient * area (m^2)

STAGES = [ # thrust N, mass flow kg/s, chamber pressure bar, tank pressure bar, temp K
    dict(thrust=7.6e6, mdot=2500.0, pc=280.0, pt=3.5, temp=3500.0),
    dict(thrust=0.95e6, mdot=310.0, pc=110.0, pt=3.0, temp=3300.0),
]

def simulate(seed: int, dt: float = 0.1, duration: float = 270.0) -> pd.DataFrame:
    """Return a DataFrame with column t plus one noisy column per sensor."""
    rng = np.random.default_rng(seed)
    n = int(duration / dt)
    mass, h, v = 550_000.0, 0.0, 0.0
    rows = []
    for i in range(n):
        t = i * dt
        stage = STAGES[0] if t < STAGING_T else STAGES[1]
        if i > 0 and abs(t - STAGING_T) < dt / 2:
            mass = 70_000.0 # stage separation: jettison stage 1
        ramp = min(1.0, t / 3.0) if t < STAGING_T else min(1.0, (t - STAGING_T) / 2.0)
        thrust = stage["thrust"] * ramp
        rho = 1.225 * np.exp(-max(h, 0.0) / 8500.0)
        drag = 0.5 * rho * v * v * CD_A
        g = G0 * (R_EARTH / (R_EARTH + h)) ** 2
        accel_proper = (thrust - drag) / mass   # what an accelerometer reads
        accel_true = accel_proper - g if (h > 0 or thrust > mass * g) else 0.0
        v += accel_true * dt
        h += v * dt
        mass -= stage["mdot"] * ramp * dt
        rows.append(dict(
            t=t, altitude=h, velocity=v, acceleration=accel_proper,
            chamber_pressure=stage["pc"] * ramp,
            tank_pressure=stage["pt"] + 0.2 * np.sin(t / 7.0),
            engine_temp=300.0 + (stage["temp"] - 300.0) * ramp,
        ))
    df = pd.DataFrame(rows)
    for s in SENSORS:
        df[s] += rng.normal(0.0, NOISE_STD[s], size=n)
    return df