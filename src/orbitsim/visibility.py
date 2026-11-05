"""Ground-station visibility and Sun-proximity (日凌) checks.

Both are geometric, circular-orbit, and reuse the β angle from ``orbit_sun``:

- Ground visibility: a circular orbit over a ground site at latitude φ_s is
  above the minimum elevation ε_min for a fraction of each pass. The classic
  closed form for the *access* (horizon-to-horizon) fraction of one orbit is

      cos(ρ) = RE / r,                      Earth central half-angle of the footprint
      λ_max = arccos( cos ρ / cos ε ),      max Earth central angle at elevation ε
      access_fraction ≈ λ_max / π            (equatorial overpass, order-of-magnitude)

  For a Sun-synchronous orbit at inclination i, a site at latitude |φ_s| ≤ i is
  overflown; we report the *daily mean access time* using the equatorial-pass
  approximation scaled by a latitude factor cos(φ_s)/cos(φ_max).

- 日凌 (Sun proximity / sun outage): a ground→satellite link suffers when the
  angular separation between the satellite line-of-sight and the Sun falls
  below a threshold (≈0.5° for Ku-band GEO; use ``sun_outage_thresh_deg``).
  Here the check is geometric and uses the same β: for a dawn–dusk orbit the
  Sun sits in/near the orbit plane, so sun-transit happens near the ascending/
  descending node when the site, satellite, and Sun align — i.e. when the
  orbit's β is small. We report the fraction of the year when
  |β| < sun_outage_thresh_deg as the sun-transit-prone window.

These are order-of-magnitude design numbers, not per-pass ephemerides.
"""

from __future__ import annotations

import math

from . import orbit_sun

RE_M = orbit_sun.RE_M
OBLIQUITY_DEG = orbit_sun.OBLIQUITY_DEG


def footprint_half_angle_deg(alt_m: float) -> float:
    """Earth central half-angle ρ of the geometric footprint [deg]."""
    r = RE_M + float(alt_m)
    return math.degrees(math.acos(RE_M / r))


def max_earth_central_angle_deg(alt_m: float, min_elevation_deg: float) -> float:
    """Max Earth central angle λ at which the sat is above ``min_elevation_deg``.

    From the spherical-Earth geometry:
        tan ε = (cos λ − RE/r) / sin λ   ⇒  solve for λ.
    Solved by fixed-point iteration (converges in <20 steps for LEO).
    """
    r = RE_M + float(alt_m)
    e = math.radians(float(min_elevation_deg))
    lam = math.acos(RE_M / r)  # start at the horizon limit
    for _ in range(50):
        f = math.cos(lam) - RE_M / r - math.tan(e) * math.sin(lam)
        df = -math.sin(lam) - math.tan(e) * math.cos(lam)
        step = f / df
        lam -= step
        if abs(step) < 1e-12:
            break
    return math.degrees(lam)


def access_fraction_equatorial(alt_m: float, min_elevation_deg: float) -> float:
    """Fraction of one orbit above min elevation, equatorial overpass."""
    lam = math.radians(max_earth_central_angle_deg(alt_m, min_elevation_deg))
    return lam / math.pi


def daily_access_minutes(
    alt_m: float,
    min_elevation_deg: float,
    site_lat_deg: float,
    inclination_deg: float,
) -> float:
    """Order-of-magnitude daily access time [min] for a site at latitude φ_s.

    A circular orbit at inclination i overflies latitudes |φ| ≤ i. We scale the
    equatorial access fraction by the orbit's daily period count and a simple
    latitude fall-off cos(φ)/cos(φ_lim), where φ_lim = min(i, 90−i·0) — the
    site latitude clipped to the orbit's reach.
    """
    i = float(inclination_deg)
    phi = float(site_lat_deg)
    if abs(phi) > i + 1e-9:
        return 0.0
    period_min = orbit_sun.chief_period_s(alt_m) / 60.0
    orbits_per_day = 1440.0 / period_min
    frac_eq = access_fraction_equatorial(alt_m, min_elevation_deg)
    # simple latitude fall-off: equator gets full, poleward edge of reach gets ~0
    lat_factor = math.cos(math.radians(phi)) / math.cos(math.radians(min(abs(phi), i)))
    # guard: at the very edge this is 0/0-ish; cap at 1
    lat_factor = min(1.0, max(0.0, lat_factor))
    return frac_eq * period_min * orbits_per_day * lat_factor


def sun_transit_prone_fraction_of_year(ltan_h: float, thresh_deg: float = 0.5) -> float:
    """Fraction of the year when |β| < ``thresh_deg`` (Sun near the orbit plane).

    For a dawn–dusk SSO (LTAN 06:00/18:00) the Sun is far from the plane most
    of the year; for a noon/midnight SSO it is in-plane. A ground link is prone
    to sun-transit outages during the low-|β| window.
    """
    inc = orbit_sun.sso_inclination_deg(orbit_sun.DEFAULT_ALT_M)
    days = 365
    prone = 0
    for d in range(1, days + 1):
        dec = orbit_sun.solar_declination_deg(d - 0.5)
        beta = orbit_sun.beta_angle_rad(inc, dec, ltan_h)
        if abs(math.degrees(beta)) < float(thresh_deg):
            prone += 1
    return prone / days


def sun_outage_season_days(ltan_h: float, thresh_deg: float = 0.5) -> int:
    """Number of days in the year with |β| below the sun-outage threshold."""
    return int(round(sun_transit_prone_fraction_of_year(ltan_h, thresh_deg) * 365))
