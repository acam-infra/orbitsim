"""Feature report: run the declared analyses over a loaded config and print a
headline table. The output definition (what counts as "the answer") lives here.

Analyses are a closed set, declared under ``analysis:`` in the YAML:

- ``orbit_eclipse``:    β threshold, per-orbit umbra minutes, three-season table
- ``year_eclipse``:     annual umbra hours, days with umbra, sunlight fraction
- ``daily_eclipse``:    per-calendar-day umbra table (summary row only here)
- ``ground_access``:    daily access minutes for a declared ground site
- ``sun_transit``:      days of year prone to sun-transit (日凌) outages
- ``constellation``:    constellation-level counts (orbits, sats, planes)
"""

from __future__ import annotations

import math

from . import orbit_sun, visibility
from .constellation import Constellation

THREE_SEASON_DECLS = (0.0, orbit_sun.OBLIQUITY_DEG, -orbit_sun.OBLIQUITY_DEG)


def _fmt(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}"


def run_analysis(spec: dict, const: Constellation) -> list[str]:
    """Dispatch one ``analysis:`` item; returns report lines."""
    kind = spec.get("kind")
    lines: list[str] = []

    if kind == "constellation":
        lines.append(f"[constellation] kind={const.kind} orbits={const.n_orbits} sats={const.n_sats}")
        for o in const.orbits[:8]:
            extra = f" ltan={o.ltan_h}" if o.ltan_h is not None else (f" raan={o.raan_deg:.0f}" if o.raan_deg is not None else "")
            lines.append(f"  {o.name:>10}: alt={o.altitude_m/1e3:.0f} km inc={o.inclination_deg:.2f} deg T={o.period_s/60:.1f} min{extra}")
        if const.n_orbits > 8:
            lines.append(f"  ... ({const.n_orbits - 8} more orbits)")
        return lines

    # the remaining analyses are per-orbit; run on each SSO/TLE orbit, and on the
    # walker shell's chief plane as representative
    for o in const.orbits:
        alt = o.altitude_m
        ltan = o.ltan_h if o.ltan_h is not None else orbit_sun.DEFAULT_LTAN_H
        inc = o.inclination_deg
        tag = f"[{kind} {o.name}]"

        if kind == "orbit_eclipse":
            thr = orbit_sun.eclipse_threshold_deg(alt)
            lines.append(f"{tag} alt={alt/1e3:.0f} km inc={inc:.2f} ltan={ltan:.2f}  no-eclipse |β|≥{_fmt(thr)} deg")
            for dec in THREE_SEASON_DECLS:
                beta = orbit_sun.beta_angle_rad(inc, dec, ltan)
                emin = orbit_sun.eclipse_minutes(alt, beta)
                season = {0.0: "equinox", orbit_sun.OBLIQUITY_DEG: "summer", -orbit_sun.OBLIQUITY_DEG: "winter"}[dec]
                lines.append(f"    {season:>7}: β={math.degrees(beta):+6.2f} deg  umbra={_fmt(emin,1)} min/orbit")
        elif kind == "year_eclipse":
            rows = orbit_sun.year_beta_series(alt, ltan)
            s = orbit_sun.summarize_year_beta(rows, alt, ltan)
            lines.append(
                f"{tag} annual_umbra={_fmt(s['annual_umbra_hours'],1)} h  "
                f"days_with_umbra={s['days_with_umbra']:.0f}/365  "
                f"sunlight={100*s['annual_sunlight_frac']:.1f}%  "
                f"max_eclipse={_fmt(s['max_eclipse_min'],1)} min (doy {s['doy_at_max_eclipse']:.0f})"
            )
        elif kind == "daily_eclipse":
            rows = orbit_sun.daily_umbra_table(alt, ltan)
            s = orbit_sun.summarize_daily_umbra(rows, alt, ltan)
            lines.append(
                f"{tag} days_in_umbra={s['days_in_umbra']:.0f}/{s['year_days']:.0f}  "
                f"peak day {s['peak_day']:.0f} {_fmt(s['peak_umbra_hours'])} h/day  "
                f"annual {_fmt(s['annual_umbra_hours'],1)} h"
            )
        elif kind == "ground_access":
            lat = float(spec["site_lat_deg"])
            el = float(spec.get("min_elevation_deg", 10.0))
            mins = visibility.daily_access_minutes(alt, el, lat, inc)
            lines.append(f"{tag} site_lat={lat:+.1f} el≥{el:.0f} deg  daily_access≈{_fmt(mins,1)} min")
        elif kind == "sun_transit":
            thr = float(spec.get("thresh_deg", 0.5))
            days = visibility.sun_outage_season_days(ltan, thr)
            lines.append(f"{tag} sun-transit-prone days (|β|<{thr} deg): {days}/365")
        else:
            raise ValueError(f"unknown analysis kind: {kind!r}")
    return lines


def run(config: dict, const: Constellation) -> str:
    name = config.get("name", "(unnamed)")
    lines = [f"orbitsim report: {name}", ""]
    for spec in config.get("analysis", []):
        lines.extend(run_analysis(spec, const))
    return "\n".join(lines)
