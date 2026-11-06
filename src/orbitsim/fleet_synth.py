"""Time-stepped synthesis of a mixed fleet: remote-sensing (RS) satellites,
compute satellites, and ground stations on a rotating Earth.

``fleet_energy`` and ``shadow_escape`` stay in the inertial frame and need no
Earth rotation. Anything that touches the ground — imaging a region,
downlinking to a station — needs sub-satellite points, so this module adds:

- J2 secular RAAN drift (SSO planes follow the Sun; a 53° shell regresses
  ~5°/day);
- Earth rotation via a mean-Sun sidereal angle:
  ``θ_G(t) = α_sun(doy) + π + 2π·t/86400``, t = UTC seconds into the day, so a
  site at longitude λ has local mean solar time ``t/3600 + λ/15``;
- ground-station elevation and satellite–satellite line of sight (the segment
  must clear ``RE + grazing_m``).

An SSO record is declared by LTAN; its RAAN on day ``doy`` is
``α_sun + (LTAN − 12 h)·15°`` — the same convention as ``fleet_energy``.

Everything is vectorised with NumPy over (time, satellite). Circular orbits,
spherical Earth, cylindrical umbra.
"""

from __future__ import annotations

import math

import numpy as np

from . import fleet_energy as fe
from . import orbit_sun as osun

RE_M = osun.RE_M
_YEAR_DAYS = 365.2422


def sun_ra_rad(doy: float) -> float:
    return 2.0 * math.pi * (float(doy) - 81.0) / _YEAR_DAYS


def raan_rate_rad_s(alt_m: float, inc_deg: float) -> float:
    a = RE_M + alt_m
    n = math.sqrt(osun.MU_M3_S2 / a ** 3)
    return -1.5 * n * osun.J2 * (RE_M / a) ** 2 * math.cos(math.radians(inc_deg))


def make_sat(name: str, alt_km: float, *, ltan_h: float | None = None,
             inc_deg: float | None = None, raan_deg: float | None = None,
             u0_deg: float = 0.0, role: str = "rs", **extra) -> dict:
    """One circular satellite. Give ``ltan_h`` for SSO (inclination auto) or
    ``inc_deg`` + ``raan_deg`` for a fixed-RAAN plane."""
    alt = alt_km * 1e3
    if ltan_h is not None:
        inc = osun.sso_inclination_deg(alt) if inc_deg is None else inc_deg
    else:
        inc = float(inc_deg)
    return {"name": name, "alt_m": alt, "inc_deg": inc, "ltan_h": ltan_h,
            "raan_deg": raan_deg, "u0_deg": u0_deg, "role": role, **extra}


def walker(prefix: str, planes: int, spp: int, alt_km: float, inc_deg: float,
           F: int = 1, raan0_deg: float = 0.0, role: str = "compute") -> list[dict]:
    out = []
    for p in range(planes):
        for k in range(spp):
            out.append(make_sat(f"{prefix}/p{p}s{k}", alt_km, inc_deg=inc_deg,
                                raan_deg=raan0_deg + 360.0 * p / planes,
                                u0_deg=360.0 * k / spp + 360.0 * F * p / planes,
                                role=role, plane=p))
    return out


def sso_plane(prefix: str, n: int, alt_km: float, ltan_h: float,
              u0_deg: float = 0.0, role: str = "compute") -> list[dict]:
    return [make_sat(f"{prefix}/s{k}", alt_km, ltan_h=ltan_h,
                     u0_deg=u0_deg + 360.0 * k / n, role=role, plane=0)
            for k in range(n)]


def positions(sats: list[dict], doy: float, t_s: np.ndarray) -> np.ndarray:
    """ECI positions [m], shape (T, N, 3)."""
    t = np.asarray(t_s, dtype=float)[:, None]
    alpha = sun_ra_rad(doy)
    raan0 = np.array([
        (alpha + math.radians((s["ltan_h"] - 12.0) * 15.0)) if s["ltan_h"] is not None
        else math.radians(s["raan_deg"]) for s in sats])
    rate = np.array([raan_rate_rad_s(s["alt_m"], s["inc_deg"]) for s in sats])
    n = np.array([fe.mean_motion_rad_s(s["alt_m"]) for s in sats])
    # RS planes declared by LTAN already include the drift implicitly at t=0;
    # within the day the J2 drift carries them with the Sun.
    raan = raan0[None, :] + rate[None, :] * t
    u = np.radians([s["u0_deg"] for s in sats])[None, :] + n[None, :] * t
    inc = np.radians([s["inc_deg"] for s in sats])[None, :]
    r = np.array([RE_M + s["alt_m"] for s in sats])[None, :]
    xo, yo = r * np.cos(u), r * np.sin(u)
    x1, y1, z1 = xo, yo * np.cos(inc), yo * np.sin(inc)
    x = x1 * np.cos(raan) - y1 * np.sin(raan)
    y = x1 * np.sin(raan) + y1 * np.cos(raan)
    return np.stack([x, y, z1], axis=-1)


def sun_vec(doy: float) -> np.ndarray:
    return np.array(fe.sun_direction(doy))


def lit(pos: np.ndarray, sun: np.ndarray) -> np.ndarray:
    d = pos @ sun
    perp = pos - d[..., None] * sun
    return ~((d < 0) & (np.einsum("...k,...k->...", perp, perp) < RE_M ** 2))


def gmst_rad(doy: float, t_s: np.ndarray) -> np.ndarray:
    return sun_ra_rad(doy) + math.pi + 2.0 * math.pi * np.asarray(t_s) / 86400.0


def subpoint(pos: np.ndarray, doy: float, t_s: np.ndarray):
    """(lat_deg, lon_deg) of each satellite, shape (T, N)."""
    r = np.linalg.norm(pos, axis=-1)
    lat = np.degrees(np.arcsin(pos[..., 2] / r))
    lon = np.degrees(np.arctan2(pos[..., 1], pos[..., 0]) - gmst_rad(doy, t_s)[:, None])
    lon = (lon + 180.0) % 360.0 - 180.0
    return lat, lon


def site_eci(lat_deg: float, lon_deg: float, doy: float, t_s: np.ndarray) -> np.ndarray:
    th = gmst_rad(doy, t_s) + math.radians(lon_deg)
    la = math.radians(lat_deg)
    return RE_M * np.stack([math.cos(la) * np.cos(th), math.cos(la) * np.sin(th),
                            np.full_like(th, math.sin(la))], axis=-1)


def elevation_deg(pos: np.ndarray, site: np.ndarray) -> np.ndarray:
    """Elevation of every satellite seen from a site, shape (T, N)."""
    d = pos - site[:, None, :]
    up = site / np.linalg.norm(site, axis=-1, keepdims=True)
    s = np.einsum("tnk,tk->tn", d, up) / np.linalg.norm(d, axis=-1)
    return np.degrees(np.arcsin(np.clip(s, -1, 1)))


def solar_elevation_deg(lat, lon, doy: float, t_s: np.ndarray) -> np.ndarray:
    """Sun elevation at the sub-satellite points, shape (T, N)."""
    la, lo = np.radians(lat), np.radians(lon) + gmst_rad(doy, t_s)[:, None]
    g = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=-1)
    return np.degrees(np.arcsin(np.clip(g @ sun_vec(doy), -1, 1)))


def los_range(pa: np.ndarray, pb: np.ndarray, grazing_m: float = 80e3):
    """Pairwise range [m] and line-of-sight flag between two fleets.

    ``pa`` (T, A, 3), ``pb`` (T, B, 3) → arrays of shape (T, A, B).
    """
    d = pb[:, None, :, :] - pa[:, :, None, :]
    L2 = np.einsum("tabk,tabk->tab", d, d)
    # closest approach of segment pa→pb to Earth centre
    s = -np.einsum("tak,tabk->tab", pa, d) / np.maximum(L2, 1.0)
    s = np.clip(s, 0.0, 1.0)
    c = pa[:, :, None, :] + s[..., None] * d
    clear = np.einsum("tabk,tabk->tab", c, c) > (RE_M + grazing_m) ** 2
    return np.sqrt(L2), clear


def runs(mask: np.ndarray, dt: float) -> list[float]:
    """Durations [s] of consecutive True runs in a 1-D boolean array."""
    out, n = [], 0
    for v in mask:
        if v:
            n += 1
        elif n:
            out.append(n * dt)
            n = 0
    if n:
        out.append(n * dt)
    return out
