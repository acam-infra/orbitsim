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
from . import isl as isl_mod

THREE_SEASON_DECLS = (0.0, orbit_sun.OBLIQUITY_DEG, -orbit_sun.OBLIQUITY_DEG)


def _fmt(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}"


def run_analysis(spec: dict, const: Constellation) -> list[str]:
    """Dispatch one ``analysis:`` item; returns report lines."""
    kind = spec.get("kind")
    lines: list[str] = []

    if kind == "constellation":
        lines.append(
            f"[constellation] shells={const.n_shells} orbits={const.n_orbits} sats={const.n_sats}")
        for sh in const.shells:
            lines.append(f"  shell {sh.name!r}: kind={sh.kind} orbits={sh.n_orbits} sats={sh.n_sats}")
            for o in sh.orbits[:4]:
                extra = (f" ltan={o.ltan_h}" if o.ltan_h is not None
                         else (f" raan={o.raan_deg:.0f}" if o.raan_deg is not None else ""))
                lines.append(
                    f"    {o.name:>16}: alt={o.altitude_m/1e3:.0f} km"
                    f" inc={o.inclination_deg:.2f} deg T={o.period_s/60:.1f} min{extra}")
            if sh.n_orbits > 4:
                lines.append(f"    ... ({sh.n_orbits - 4} more orbits)")
        return lines

    if kind == "isl_topology":
        # Accept either the flat form (mode: positive_grid) or the paired form
        # (intra_shell: {...} / inter_shell: {...}).
        if "intra_shell" in spec or "inter_shell" in spec:
            mode: dict = {}
            if "intra_shell" in spec:
                mode["intra_shell"] = dict(spec["intra_shell"])
            if "inter_shell" in spec:
                mode["inter_shell"] = dict(spec["inter_shell"])
            mode_desc = (
                f"intra={mode.get('intra_shell', {}).get('kind', 'bent_pipe')}"
                f" inter={mode.get('inter_shell', {}).get('kind', 'bent_pipe')}"
            )
        else:
            mode = {"kind": spec.get("mode", "positive_grid")}
            if "n" in spec:
                mode["n"] = spec["n"]
            if "max_range_km" in spec:
                mode["max_range_km"] = spec["max_range_km"]
            mode_desc = f"mode={mode['kind']}" + (f" n={mode['n']}" if "n" in mode else "")
        edges = isl_mod.build_edges(const, mode)
        s = isl_mod.summarize_edges(const, edges)
        lines.append(
            f"[isl_topology] {mode_desc}"
            + f"  shells={s['n_shells']} sats={s['n_sats']} edges={s['n_edges']}"
        )
        lines.append(
            f"    per-plane:  intra {s['intra_plane_edges']}, inter {s['inter_plane_edges']}"
        )
        if s["n_shells"] > 1:
            lines.append(
                f"    per-shell:  intra {s['intra_shell_edges']}, inter {s['inter_shell_edges']}"
            )
        lines.append(
            f"    degree min/mean/max = {s['degree_min']}/{s['degree_mean']:.2f}/{s['degree_max']}"
            + f"   link km min/mean/max = {s['link_km_min']:.0f}/{s['link_km_mean']:.0f}/{s['link_km_max']:.0f}"
        )
        if spec.get("list_edges"):
            for e in edges[: int(spec.get("list_edges", 0))]:
                tag = "intra-plane" if e["intra_plane"] else (
                    "intra-shell" if e.get("intra_shell", True) else "inter-shell")
                lines.append(f"    {e['a']:>14} -- {e['b']:<14} {e['distance_km']:8.0f} km  ({tag})")
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
