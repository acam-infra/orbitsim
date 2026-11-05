"""Constellation declarations: how a set of orbits is described and expanded.

Three kinds, closed set — pick one per ``constellation:`` block:

- ``sso``:      one sun-synchronous circular orbit (altitude + LTAN). This is
                what the β/umbra analysis in ``orbit_sun`` is built on.
- ``walker``:   a Walker-delta shell (planes × sats_per_plane, altitude,
                inclination). Used for constellation-level features (count,
                coverage geometry), not per-sat umbra.
- ``tle``:      a list of TLE pairs, expanded into named orbits. Kept minimal:
                mean motion → altitude, inclination from line 2.

Each expands into a list of ``Orbit`` records; constellation-level features
(``features``) are computed on that list.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import orbit_sun

MU_M3_S2 = orbit_sun.MU_M3_S2
RE_M = orbit_sun.RE_M


@dataclass(frozen=True)
class Orbit:
    """One orbit in the constellation (a plane, or a single sat for sso)."""

    name: str
    altitude_m: float
    inclination_deg: float
    ltan_h: float | None = None      # only for SSO
    raan_deg: float | None = None    # only for walker planes
    kind: str = "sso"

    @property
    def period_s(self) -> float:
        return orbit_sun.chief_period_s(self.altitude_m)


@dataclass(frozen=True)
class Constellation:
    kind: str
    orbits: tuple[Orbit, ...]
    params: dict = field(default_factory=dict)

    @property
    def n_orbits(self) -> int:
        return len(self.orbits)

    @property
    def n_sats(self) -> int:
        if self.kind == "walker":
            return int(self.params.get("planes", 1)) * int(self.params.get("sats_per_plane", 1))
        return self.n_orbits


def _alt_from_mean_motion(revs_per_day: float) -> float:
    """Altitude [m] from TLE mean motion (rev/day), circular orbit."""
    n = float(revs_per_day) * 2.0 * math.pi / 86400.0  # rad/s
    a = (MU_M3_S2 / (n * n)) ** (1.0 / 3.0)
    return a - RE_M


def from_sso(altitude_m: float, ltan_h: float, name: str = "sso0") -> Constellation:
    inc = orbit_sun.sso_inclination_deg(altitude_m)
    return Constellation(
        kind="sso",
        orbits=(Orbit(name=name, altitude_m=altitude_m, inclination_deg=inc,
                      ltan_h=ltan_h, kind="sso"),),
        params={"altitude_m": altitude_m, "ltan_h": ltan_h},
    )


def from_walker(planes: int, sats_per_plane: int, altitude_m: float,
                inclination_deg: float) -> Constellation:
    if planes <= 0 or sats_per_plane <= 0:
        raise ValueError("walker planes/sats_per_plane must be > 0")
    orbits = tuple(
        Orbit(name=f"plane{p}", altitude_m=altitude_m, inclination_deg=inclination_deg,
              raan_deg=360.0 * p / planes, kind="walker")
        for p in range(int(planes))
    )
    return Constellation(
        kind="walker",
        orbits=orbits,
        params={"planes": int(planes), "sats_per_plane": int(sats_per_plane),
                "altitude_m": altitude_m, "inclination_deg": inclination_deg},
    )


def from_tle(tles: list[dict]) -> Constellation:
    """``tles``: [{"name": ..., "l1": ..., "l2": ...}]"""
    orbits = []
    for i, t in enumerate(tles):
        l2 = t["l2"].split()
        inc = float(l2[2])
        mm = float(l2[7])
        orbits.append(Orbit(
            name=t.get("name", f"tle{i}"),
            altitude_m=_alt_from_mean_motion(mm),
            inclination_deg=inc,
            kind="tle",
        ))
    return Constellation(kind="tle", orbits=tuple(orbits), params={"count": len(orbits)})


def load_constellation(cfg: dict) -> Constellation:
    """Validate a ``constellation:`` mapping into a ``Constellation``."""
    raw = dict(cfg or {})
    kind = raw.pop("kind", None)
    if kind == "sso":
        return from_sso(float(raw["altitude_m"]), float(raw["ltan_h"]),
                        str(raw.get("name", "sso0")))
    if kind == "walker":
        return from_walker(int(raw["planes"]), int(raw["sats_per_plane"]),
                           float(raw["altitude_m"]), float(raw["inclination_deg"]))
    if kind == "tle":
        return from_tle(list(raw["tles"]))
    raise ValueError(f"constellation.kind must be one of sso|walker|tle, got {kind!r}")
