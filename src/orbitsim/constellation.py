"""Constellation declarations: how a set of orbits is described and expanded.

Three per-shell kinds, closed set:

- ``sso``:      one sun-synchronous circular orbit (altitude + LTAN). This is
                what the β/umbra analysis in ``orbit_sun`` is built on.
- ``walker``:   a Walker-delta shell (planes × sats_per_plane, altitude,
                inclination). Used for constellation-level features (count,
                coverage geometry), not per-sat umbra.
- ``tle``:      a list of TLE pairs, expanded into named orbits. Kept minimal:
                mean motion → altitude, inclination from line 2.

A ``constellation:`` block is either a single shell (one of the kinds above)
or a multi-shell declaration::

    constellation:
      shells:
        - {name: sh1, kind: walker, planes: 72, sats_per_plane: 22, ...}
        - {name: sh2, kind: walker, planes: 36, sats_per_plane: 20, ...}

Single-shell YAML is sugar for ``shells: [<one entry>]`` — internally a
``Constellation`` is always a list of ``Shell`` records. This mirrors
StarPerf 2.0, where a scenario file lists several shells (Starlink's five,
OneWeb's two, Telesat's two) and ISL is built intra-shell by construction
and inter-shell by distance search.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import orbit_sun

MU_M3_S2 = orbit_sun.MU_M3_S2
RE_M = orbit_sun.RE_M


@dataclass(frozen=True)
class Orbit:
    """One orbit in a shell (a plane, or a single sat for sso)."""

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
class Shell:
    """One orbital shell: a named set of orbits at one altitude/inclination.

    Multi-shell constellations (Starlink's five shells, OneWeb's two) are
    modelled as a list of these. ``name`` prefixes every expanded satellite
    so cross-shell edges are identifiable by name alone (``sh1/p0s0``).
    """

    name: str
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


@dataclass(frozen=True)
class Constellation:
    """A whole constellation: one or more shells.

    The ``kind``/``orbits``/``params`` attributes mirror the first shell for
    backward compatibility with single-shell code; new code should iterate
    ``shells`` instead.
    """

    shells: tuple[Shell, ...]

    @property
    def kind(self) -> str:
        return "multi" if len(self.shells) > 1 else self.shells[0].kind

    @property
    def orbits(self) -> tuple[Orbit, ...]:
        return tuple(o for sh in self.shells for o in sh.orbits)

    @property
    def params(self) -> dict:
        return self.shells[0].params if self.shells else {}

    @property
    def n_orbits(self) -> int:
        return sum(sh.n_orbits for sh in self.shells)

    @property
    def n_sats(self) -> int:
        return sum(sh.n_sats for sh in self.shells)

    @property
    def n_shells(self) -> int:
        return len(self.shells)


def _alt_from_mean_motion(revs_per_day: float) -> float:
    """Altitude [m] from TLE mean motion (rev/day), circular orbit."""
    n = float(revs_per_day) * 2.0 * math.pi / 86400.0  # rad/s
    a = (MU_M3_S2 / (n * n)) ** (1.0 / 3.0)
    return a - RE_M


def _build_sso_shell(name: str, altitude_m: float, ltan_h: float) -> Shell:
    inc = orbit_sun.sso_inclination_deg(altitude_m)
    return Shell(
        name=name,
        kind="sso",
        orbits=(Orbit(name=f"{name}/sso0", altitude_m=altitude_m, inclination_deg=inc,
                      ltan_h=ltan_h, kind="sso"),),
        params={"altitude_m": altitude_m, "ltan_h": ltan_h},
    )


def _build_walker_shell(name: str, planes: int, sats_per_plane: int,
                        altitude_m: float, inclination_deg: float,
                        phase_factor: int = 1,
                        raan_offset_deg: float = 0.0,
                        phase_offset_deg: float = 0.0) -> Shell:
    """Walker-delta shell ``planes × sats_per_plane`` with phasing factor ``F``.

    Satellite (p, k) has RAAN ``raan_offset + 360°·p/planes`` and in-plane
    phase ``360°·k/spp + 360°·F·p/planes`` — the standard Walker δ pattern,
    which staggers adjacent planes so same-index satellites do not coincide.

    ``raan_offset_deg`` rotates the whole shell's RAAN grid and
    ``phase_offset_deg`` shifts every satellite's in-plane argument. They
    matter when two shells share (altitude, inclination): a RAAN offset alone
    is NOT enough to keep t=0 positions distinct, because for a circular
    orbit (Ω, u) and (Ω+180°, u+180°) are the *same* point in space for any
    inclination — so a shell shifted only in RAAN still lands on the other
    shell's satellites half a plane away. Pair a RAAN offset with a
    ``phase_offset_deg`` (half the in-plane spacing, 180°/spp, works well) to
    break that symmetry; otherwise a distance-based inter-shell search
    reports zero-length links.
    """
    if planes <= 0 or sats_per_plane <= 0:
        raise ValueError("walker planes/sats_per_plane must be > 0")
    off = float(raan_offset_deg)
    orbits = tuple(
        Orbit(name=f"{name}/plane{p}", altitude_m=altitude_m,
              inclination_deg=inclination_deg,
              raan_deg=(off + 360.0 * p / planes) % 360.0, kind="walker")
        for p in range(int(planes))
    )
    return Shell(
        name=name,
        kind="walker",
        orbits=orbits,
        params={"planes": int(planes), "sats_per_plane": int(sats_per_plane),
                "altitude_m": altitude_m, "inclination_deg": inclination_deg,
                "phase_factor": int(phase_factor), "raan_offset_deg": off,
                "phase_offset_deg": float(phase_offset_deg)},
    )


def _build_tle_shell(name: str, tles: list[dict]) -> Shell:
    """``tles``: [{"name": ..., "l1": ..., "l2": ...}]"""
    orbits = []
    for i, t in enumerate(tles):
        l2 = t["l2"].split()
        inc = float(l2[2])
        mm = float(l2[7])
        orbits.append(Orbit(
            name=f"{name}/{t.get('name', f'tle{i}')}",
            altitude_m=_alt_from_mean_motion(mm),
            inclination_deg=inc,
            kind="tle",
        ))
    return Shell(name=name, kind="tle", orbits=tuple(orbits),
                 params={"count": len(orbits)})


def _build_shell(raw: dict, default_name: str) -> Shell:
    """Validate one shell mapping into a ``Shell``."""
    spec = dict(raw or {})
    name = str(spec.pop("name", default_name))
    kind = spec.pop("kind", None)
    if kind == "sso":
        return _build_sso_shell(name, float(spec["altitude_m"]),
                                float(spec["ltan_h"]))
    if kind == "walker":
        return _build_walker_shell(
            name,
            int(spec["planes"]), int(spec["sats_per_plane"]),
            float(spec["altitude_m"]), float(spec["inclination_deg"]),
            int(spec.get("phase_factor", 1)),
            float(spec.get("raan_offset_deg", 0.0)),
            float(spec.get("phase_offset_deg", 0.0)),
        )
    if kind == "tle":
        return _build_tle_shell(name, list(spec["tles"]))
    raise ValueError(f"shell.kind must be one of sso|walker|tle, got {kind!r}")


def from_sso(altitude_m: float, ltan_h: float, name: str = "sso0") -> Constellation:
    """Single SSO shell. Kept for backward compatibility with single-shell callers."""
    return Constellation(shells=(_build_sso_shell(name, altitude_m, ltan_h),))


def from_walker(planes: int, sats_per_plane: int, altitude_m: float,
                inclination_deg: float, phase_factor: int = 1) -> Constellation:
    """Single Walker-delta shell. Backward-compat wrapper."""
    return Constellation(shells=(_build_walker_shell(
        "sh0", planes, sats_per_plane, altitude_m, inclination_deg, phase_factor),))


def from_tle(tles: list[dict]) -> Constellation:
    """Single TLE shell. Backward-compat wrapper."""
    return Constellation(shells=(_build_tle_shell("sh0", tles),))


def from_shells(shells: list[Shell]) -> Constellation:
    if not shells:
        raise ValueError("constellation must have at least one shell")
    return Constellation(shells=tuple(shells))


def load_constellation(cfg: dict) -> Constellation:
    """Validate a ``constellation:`` mapping into a ``Constellation``.

    Accepts either a single-shell mapping (``kind: walker|sso|tle`` at the top
    level) or a multi-shell mapping (``shells: [...]``). The two are mutually
    exclusive.
    """
    raw = dict(cfg or {})
    if "shells" in raw:
        if "kind" in raw:
            raise ValueError("constellation: use either `shells:` or top-level `kind:`, not both")
        entries = list(raw["shells"])
        if not entries:
            raise ValueError("constellation.shells must be non-empty")
        names = [str(e.get("name", f"sh{i}")) for i, e in enumerate(entries)]
        if len(set(names)) != len(names):
            raise ValueError(f"constellation.shells names must be unique, got {names}")
        return from_shells([_build_shell(e, f"sh{i}") for i, e in enumerate(entries)])
    # single-shell sugar
    return from_shells([_build_shell(raw, "sh0")])


def expand_satellites(const: Constellation) -> list[dict]:
    """Expand a constellation into per-satellite orbital-element records.

    One dict per satellite with keys ``{name, shell, plane, index_in_plane,
    altitude_m, inclination_deg, raan_deg, phase_deg}``. Satellite names are
    prefixed with the shell name (``sh1/p0s0``) so cross-shell edges are
    identifiable by name alone. ``phase_deg`` is the in-plane argument at t=0.
    """
    sats: list[dict] = []
    for shell in const.shells:
        if shell.kind == "walker":
            planes = int(shell.params["planes"])
            spp = int(shell.params["sats_per_plane"])
            f = int(shell.params.get("phase_factor", 1))
            raan_off = float(shell.params.get("raan_offset_deg", 0.0))
            phase_off = float(shell.params.get("phase_offset_deg", 0.0))
            for p in range(planes):
                for k in range(spp):
                    sats.append({
                        "name": f"{shell.name}/p{p}s{k}",
                        "shell": shell.name,
                        "plane": p,
                        "index_in_plane": k,
                        "altitude_m": shell.params["altitude_m"],
                        "inclination_deg": shell.params["inclination_deg"],
                        "raan_deg": (raan_off + 360.0 * p / planes) % 360.0,
                        "phase_deg": (phase_off + 360.0 * k / spp
                                      + 360.0 * f * p / planes) % 360.0,
                    })
        else:
            for i, o in enumerate(shell.orbits):
                sats.append({
                    "name": o.name,
                    "shell": shell.name,
                    "plane": 0,
                    "index_in_plane": i,
                    "altitude_m": o.altitude_m,
                    "inclination_deg": o.inclination_deg,
                    "raan_deg": o.raan_deg if o.raan_deg is not None else 0.0,
                    "phase_deg": 0.0,
                })
    return sats
