"""Sun–orbit geometry: the β angle, Earth-umbra (日影) windows, and the
dawn-dusk all-year-clear altitude.

Circular orbit, spherical Earth, cylindrical umbra, penumbra ignored (the
penumbra half-angle is ~0.27°, ≈10 s per edge at 650 km — small next to the
~35 min umbra of a morning SSO).

    sin β = sin i · cos δ · sin Δ + cos i · sin δ,   Δ = (LTAN − 12 h)·15°
    no eclipse:  |β| ≥ asin(RE / r)
    fraction:    arccos(√(r² − RE²) / (r cos β)) / π   otherwise

β is the only orbit quantity the umbra depends on, and it is also what a
Sun-proximity (日凌) check needs — so it is computed once here and shared.

Units: SI (m, s, rad); ``*_deg`` / ``*_h`` suffixes are explicit in names.
"""

from __future__ import annotations

import math

MU_M3_S2 = 3.986008e14
RE_M = 6378135.0
J2 = 1.082616e-3

OBLIQUITY_DEG = 23.44          # mean solar-declination amplitude (±)
DEFAULT_ALT_M = 650e3
DEFAULT_LTAN_H = 6.0           # dawn–dusk
DEFAULT_DECLINATION_DEG = 0.0  # equinox

_SOLAR_DAY_S = 86400.0
_YEAR_DAYS = 365.2422
_SUN_RAAN_RATE = 2.0 * math.pi / (_YEAR_DAYS * _SOLAR_DAY_S)  # mean solar motion [rad/s]


def chief_period_s(alt_m: float = DEFAULT_ALT_M) -> float:
    """Kepler period of the circular chief at ``alt_m`` [s]."""
    a = RE_M + float(alt_m)
    return 2.0 * math.pi / math.sqrt(MU_M3_S2 / (a ** 3))


def sso_inclination_deg(alt_m: float = DEFAULT_ALT_M) -> float:
    """Sun-synchronous inclination [deg] of a circular orbit at ``alt_m``.

    Sets the J2 secular RAAN drift equal to the mean solar motion (retrograde ⇒
    cos i < 0). 98.0° at 650 km, 101.4° at 1400 km.
    """
    a = RE_M + float(alt_m)
    n = math.sqrt(MU_M3_S2 / (a ** 3))
    cos_i = -(2.0 / 3.0) * _SUN_RAAN_RATE / (J2 * n * (RE_M / a) ** 2)
    return math.degrees(math.acos(min(1.0, max(-1.0, cos_i))))


def solar_declination_deg(doy: float) -> float:
    """Mean solar declination [deg] at day-of-year ``doy`` (0 = 1 Jan)."""
    return OBLIQUITY_DEG * math.sin(2.0 * math.pi * (float(doy) - 81.0) / _YEAR_DAYS)


def beta_angle_rad(inclination_deg: float, declination_deg: float, ltan_h: float = DEFAULT_LTAN_H) -> float:
    """β [rad] — angle between the Sun vector and the orbit plane."""
    delta = math.radians((float(ltan_h) - 12.0) * 15.0)
    s = (
        math.sin(math.radians(inclination_deg)) * math.cos(math.radians(declination_deg)) * math.sin(delta)
        + math.cos(math.radians(inclination_deg)) * math.sin(math.radians(declination_deg))
    )
    return math.asin(min(1.0, max(-1.0, s)))


def eclipse_threshold_deg(alt_m: float = DEFAULT_ALT_M) -> float:
    """|β| at or above which the orbit never enters the umbra [deg]."""
    return math.degrees(math.asin(RE_M / (RE_M + float(alt_m))))


def eclipse_fraction(alt_m: float = DEFAULT_ALT_M, beta_rad: float = 0.0) -> float:
    """Fraction of one orbit spent in the umbra (0 once |β| reaches the threshold)."""
    r = RE_M + float(alt_m)
    b = abs(float(beta_rad))
    if b >= math.radians(eclipse_threshold_deg(alt_m)):
        return 0.0
    u = math.sqrt(r * r - RE_M * RE_M) / (r * math.cos(b))
    if u >= 1.0:
        return 0.0
    return math.acos(min(1.0, max(-1.0, u))) / math.pi


def eclipse_minutes(alt_m: float, beta_rad: float, period_s: float | None = None) -> float:
    """Umbra duration per orbit [min]."""
    period = chief_period_s(alt_m) if period_s is None else float(period_s)
    return eclipse_fraction(alt_m, beta_rad) * period / 60.0


def dawn_dusk_min_abs_beta_rad(alt_m: float = DEFAULT_ALT_M) -> float:
    """Annual minimum |β| of a dawn–dusk (LTAN 06:00) SSO at ``alt_m``."""
    inc = sso_inclination_deg(alt_m)
    return min(
        abs(beta_angle_rad(inc, +OBLIQUITY_DEG, 6.0)),
        abs(beta_angle_rad(inc, -OBLIQUITY_DEG, 6.0)),
    )


def dawn_dusk_clear_altitude_m(lo: float = 300e3, hi: float = 3000e3, tol: float = 1.0) -> float:
    """Altitude [m] at which a dawn–dusk orbit clears the umbra all year."""

    def f(h: float) -> float:
        return dawn_dusk_min_abs_beta_rad(h) - math.radians(eclipse_threshold_deg(h))

    if f(lo) >= 0.0:
        return lo
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if f(mid) >= 0.0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def year_beta_series(
    alt_m: float = DEFAULT_ALT_M,
    ltan_h: float = DEFAULT_LTAN_H,
    doy_step: float = 0.25,
) -> list[dict[str, float]]:
    """Sample β and cylindrical-umbra metrics over one tropical year."""
    step = float(doy_step)
    if not step > 0.0:
        raise ValueError(f"doy_step must be > 0, got {doy_step}")
    alt = float(alt_m)
    ltan = float(ltan_h)
    inc = sso_inclination_deg(alt)
    period_s = chief_period_s(alt)
    period_min = period_s / 60.0
    rows: list[dict[str, float]] = []
    doy = 0.0
    while doy < _YEAR_DAYS - 1e-12:
        delta = solar_declination_deg(doy)
        beta = beta_angle_rad(inc, delta, ltan)
        frac = eclipse_fraction(alt, beta)
        emin = eclipse_minutes(alt, beta, period_s)
        orbits = (step * _SOLAR_DAY_S) / period_s
        rows.append({
            "doy": doy,
            "declination_deg": delta,
            "beta_deg": math.degrees(beta),
            "abs_beta_deg": abs(math.degrees(beta)),
            "eclipse_min": emin,
            "eclipse_frac": frac,
            "umbra_hours_window": (emin / 60.0) * orbits,
            "period_min": period_min,
        })
        doy += step
    return rows


def summarize_year_beta(rows: list[dict[str, float]], alt_m: float, ltan_h: float) -> dict[str, float]:
    """Aggregate a ``year_beta_series`` table into annual headline numbers."""
    if not rows:
        raise ValueError("rows must be non-empty")
    alt = float(alt_m)
    period_s = chief_period_s(alt)
    beta_crit = eclipse_threshold_deg(alt)
    min_row = min(rows, key=lambda r: r["abs_beta_deg"])
    max_ecl = max(rows, key=lambda r: r["eclipse_min"])
    annual_umbra_h = sum(r["umbra_hours_window"] for r in rows)
    last_day = int(_YEAR_DAYS) - 1
    days_with = {min(int(r["doy"]), last_day) for r in rows if r["eclipse_min"] > 1e-9}
    return {
        "altitude_m": alt,
        "ltan_h": float(ltan_h),
        "inclination_deg": sso_inclination_deg(alt),
        "period_min": period_s / 60.0,
        "beta_crit_deg": beta_crit,
        "min_abs_beta_deg": min_row["abs_beta_deg"],
        "doy_at_min_abs_beta": min_row["doy"],
        "max_eclipse_min": max_ecl["eclipse_min"],
        "doy_at_max_eclipse": max_ecl["doy"],
        "annual_umbra_hours": annual_umbra_h,
        "days_with_umbra": float(len(days_with)),
        "eclipse_free_days": float(int(_YEAR_DAYS) - len(days_with)),
        "annual_sunlight_frac": 1.0 - (annual_umbra_h / (_YEAR_DAYS * 24.0)),
        "clears_year": 1.0 if min_row["abs_beta_deg"] >= beta_crit - 1e-9 else 0.0,
    }


def daily_umbra_table(
    alt_m: float = DEFAULT_ALT_M,
    ltan_h: float = DEFAULT_LTAN_H,
    sub_day: float = 0.02,
    year_days: int = 365,
) -> list[dict[str, float]]:
    """Umbra per calendar day over a ``year_days``-day year."""
    step = float(sub_day)
    if not step > 0.0:
        raise ValueError(f"sub_day must be > 0, got {sub_day}")
    days = int(year_days)
    if not days > 0:
        raise ValueError(f"year_days must be > 0, got {year_days}")
    alt = float(alt_m)
    ltan = float(ltan_h)
    inc = sso_inclination_deg(alt)
    period_s = chief_period_s(alt)
    rows: list[dict[str, float]] = []
    for day in range(1, days + 1):
        t = float(day - 1)
        end = float(day)
        umbra_h = 0.0
        max_emin = 0.0
        orbits = 0.0
        orbits_umbra = 0.0
        while t < end - 1e-9:
            span = min(step, end - t)
            frac = eclipse_fraction(alt, beta_angle_rad(inc, solar_declination_deg(t + 0.5 * span), ltan))
            emin = frac * period_s / 60.0
            n_orbits = span * _SOLAR_DAY_S / period_s
            umbra_h += (emin / 60.0) * n_orbits
            orbits += n_orbits
            orbits_umbra += n_orbits if frac > 0.0 else 0.0
            max_emin = max(max_emin, emin)
            t += span
        rows.append({
            "day": float(day),
            "declination_deg": solar_declination_deg(day - 0.5),
            "beta_deg": math.degrees(beta_angle_rad(inc, solar_declination_deg(day - 0.5), ltan)),
            "umbra_hours": umbra_h,
            "sunlit_hours": 24.0 - umbra_h,
            "max_eclipse_min": max_emin,
            "orbits": orbits,
            "orbits_in_umbra": orbits_umbra,
        })
    return rows


def summarize_daily_umbra(rows: list[dict[str, float]], alt_m: float, ltan_h: float) -> dict[str, float]:
    """Day-count headline numbers from a ``daily_umbra_table``."""
    if not rows:
        raise ValueError("rows must be non-empty")
    total = float(len(rows))
    shadowed = [r for r in rows if r["umbra_hours"] > 1e-9]
    peak = max(rows, key=lambda r: r["umbra_hours"])
    annual_h = sum(r["umbra_hours"] for r in rows)
    return {
        "altitude_m": float(alt_m),
        "ltan_h": float(ltan_h),
        "year_days": total,
        "days_in_umbra": float(len(shadowed)),
        "days_sunlit": total - len(shadowed),
        "season_days_frac": len(shadowed) / total,
        "annual_umbra_hours": annual_h,
        "annual_sunlight_frac": 1.0 - annual_h / (total * 24.0),
        "peak_day": peak["day"],
        "peak_umbra_hours": peak["umbra_hours"],
        "mean_umbra_hours_shadowed": (
            sum(r["umbra_hours"] for r in shadowed) / len(shadowed) if shadowed else 0.0
        ),
        "orbits_year": sum(r["orbits"] for r in rows),
        "orbits_in_umbra_year": sum(r["orbits_in_umbra"] for r in rows),
    }
