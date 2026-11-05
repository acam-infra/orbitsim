"""Fleet-level illumination: how the lit/shadowed count of a whole
constellation evolves in time.

``orbit_sun`` answers the *single-orbit* question — how many minutes of one
revolution a given β spends in the umbra. A constellation is different: the
RAAN grid of a Walker shell spreads the planes across every local solar time,
so at any instant some planes sit near dawn–dusk (large |β|, fully lit) while
others sit near noon/midnight (β ≈ 0, deepest eclipse). "Dawn–dusk SSO" is a
property of *two planes only* — there is no such thing as an all-dawn-dusk
Walker shell. From the fleet's point of view the illumination states are
therefore *decorrelated by construction*, and the interesting numbers are:

- the **power valley**: the minimum number of lit satellites over a day/year,
  i.e. how many satellites are guaranteed to be on sunlight (usable for
  compute / relay) at the worst instant;
- the **mean lit fraction** and its seasonal swing;
- whether *heterogeneous* shells (different altitude / phase offset) smooth
  the valley compared with a single homogeneous shell.

Geometry. Circular orbits, spherical Earth, cylindrical umbra — the same
model as ``orbit_sun``, but evaluated instantaneously with 3-D vectors so
that heterogeneous shells need no per-shell LTAN bookkeeping:

    sun(s)   — unit ECI vector from the mean declination/right-ascension model
    pos(sat) — ECI position from (raan, inc, u0 + n·t)
    in umbra ⟺  pos·sun < 0  AND  |pos − (pos·sun)·sun| < RE

A satellite's equivalent LTAN is an *output* here (12 h + (Ω − α_sun)/15°),
not an input — which is exactly why mixed-altitude fleets compose cleanly.

Units: SI (m, s, rad) with explicit ``*_deg`` / ``*_km`` suffixes.
"""

from __future__ import annotations

import math

from . import orbit_sun

MU_M3_S2 = orbit_sun.MU_M3_S2
RE_M = orbit_sun.RE_M
OBLIQUITY_RAD = math.radians(orbit_sun.OBLIQUITY_DEG)
_YEAR_DAYS = 365.2422


def sun_direction(doy: float) -> tuple[float, float, float]:
    """Unit ECI vector toward the Sun at day-of-year ``doy`` (0 = 1 Jan).

    Right ascension α = 2π·(doy − 81)/365.2422 (vernal equinox near doy 81),
    declination δ matches ``orbit_sun.solar_declination_deg``.
    """
    th = 2.0 * math.pi * (float(doy) - 81.0) / _YEAR_DAYS
    dec = OBLIQUITY_RAD * math.sin(th)
    return (math.cos(dec) * math.cos(th), math.cos(dec) * math.sin(th), math.sin(dec))


def sat_position(raan_deg: float, inclination_deg: float, u_deg: float,
                 alt_m: float) -> tuple[float, float, float]:
    """ECI position of a circular satellite at argument of latitude ``u_deg``."""
    r = RE_M + float(alt_m)
    raan = math.radians(raan_deg)
    inc = math.radians(inclination_deg)
    u = math.radians(u_deg)
    x_o, y_o = r * math.cos(u), r * math.sin(u)
    # rotate by inclination about x, then by RAAN about z
    x1 = x_o
    y1 = y_o * math.cos(inc)
    z1 = y_o * math.sin(inc)
    return (x1 * math.cos(raan) - y1 * math.sin(raan),
            x1 * math.sin(raan) + y1 * math.cos(raan),
            z1)


def in_umbra(pos: tuple[float, float, float],
             sun: tuple[float, float, float]) -> bool:
    """Cylindrical-umbra test: behind the Earth AND within RE of the Sun axis."""
    d = pos[0] * sun[0] + pos[1] * sun[1] + pos[2] * sun[2]
    if d >= 0.0:
        return False
    px = pos[0] - d * sun[0]
    py = pos[1] - d * sun[1]
    pz = pos[2] - d * sun[2]
    return px * px + py * py + pz * pz < RE_M * RE_M


def equivalent_ltan_h(raan_deg: float, doy: float) -> float:
    """Local time of ascending node implied by geometry [h] — a diagnostic.

    12 h + (Ω − α_sun)/15°, folded into [0, 24). Useful for labelling a
    plane's illumination regime ("this plane is the dawn-dusk one today").
    """
    th = 2.0 * math.pi * (float(doy) - 81.0) / _YEAR_DAYS
    alpha_sun_deg = math.degrees(th) % 360.0
    return (12.0 + (float(raan_deg) - alpha_sun_deg) / 15.0) % 24.0


def mean_motion_rad_s(alt_m: float) -> float:
    """Kepler mean motion of the circular orbit [rad/s]."""
    a = RE_M + float(alt_m)
    return math.sqrt(MU_M3_S2 / (a ** 3))


def lit_mask(sats: list[dict], doy: float, t_s: float) -> list[bool]:
    """Instantaneous lit(True)/shadowed(False) for every expanded satellite.

    ``sats`` comes from ``constellation.expand_satellites``; each record needs
    ``raan_deg``, ``inclination_deg``, ``phase_deg`` (u at t = 0) and
    ``altitude_m``. Phase advances with the satellite's own mean motion, so
    shells at different altitudes drift past each other exactly as they
    should — heterogeneity costs nothing here.
    """
    sun = sun_direction(doy)
    out: list[bool] = []
    for s in sats:
        u = (float(s["phase_deg"])
             + math.degrees(mean_motion_rad_s(float(s["altitude_m"])) * t_s)) % 360.0
        pos = sat_position(s["raan_deg"], s["inclination_deg"], u, s["altitude_m"])
        out.append(not in_umbra(pos, sun))
    return out


def daily_profile(sats: list[dict], doy: float, n_slots: int = 96) -> list[int]:
    """Lit-satellite count at ``n_slots`` evenly spaced instants of one day."""
    return [sum(lit_mask(sats, doy, 86400.0 * k / n_slots)) for k in range(n_slots)]


def annual_summary(sats: list[dict], n_days: int = 365,
                   n_slots: int = 96) -> list[dict]:
    """Per-day fleet illumination statistics over a year.

    One dict per day: ``{doy, lit_min, lit_mean, lit_max}`` — counts of lit
    satellites. ``lit_min`` is the power valley depth for that day; its annual
    minimum is the constellation's worst-case guaranteed-sunlit count.
    """
    days: list[dict] = []
    for doy in range(int(n_days)):
        prof = daily_profile(sats, doy, n_slots)
        days.append({
            "doy": doy,
            "lit_min": min(prof),
            "lit_mean": sum(prof) / len(prof),
            "lit_max": max(prof),
        })
    return days
