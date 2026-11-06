"""Shadow escape: how far a request must travel over the ISL grid to leave
the Earth umbra, and how long it could have waited instead.

``fleet_energy`` counts lit satellites. A migration policy needs more than a
count: when satellite *s* enters the umbra (and its compute is power-capped or
switched off), where is the nearest lit satellite on the ISL graph, and how
much lit time does that satellite have left? This module answers that with
closed-form geometry — no time stepping.

Shadow arc (closed form). For a circular orbit with node vector P, in-plane
vector Q and normal W, the Sun direction s has ``sin β = s·W`` and in-plane
azimuth ``u_s = atan2(s·Q, s·P)``. A satellite at argument of latitude u has
``pos·s = r cos β cos(u − u_s)``; the cylindrical-umbra test reduces to

    shadowed ⟺ cos(u − u_s) < −√(r² − RE²) / (r cos β)

i.e. an arc centred on ``u_s + 180°`` with half-width
``w = arccos(√(r² − RE²) / (r cos β))`` — the same w whose ``w/π`` is
``orbit_sun.eclipse_fraction``. Remaining lit / shadowed time of any satellite
is then an angular distance divided by its mean motion.

The Sun moves ~1°/day, so the arc is treated as fixed over one orbit.

Graph quantities (on a ``positive_grid`` +Grid):

- ``escape_hops``: multi-source BFS from the lit set — hop distance from each
  shadowed satellite to its nearest lit satellite (no capacity limit);
- ``capacitated_offload``: every shadowed satellite must hand its load to a
  lit satellite that absorbs at most ``k`` extra loads; greedy nearest-first
  assignment, so the returned hop counts are an upper bound on the optimum.
"""

from __future__ import annotations

import math
from collections import deque

from . import fleet_energy as fe
from .orbit_sun import RE_M


def _plane_frame(raan_deg: float, inclination_deg: float):
    raan = math.radians(raan_deg)
    inc = math.radians(inclination_deg)
    p = (math.cos(raan), math.sin(raan), 0.0)
    q = (-math.sin(raan) * math.cos(inc), math.cos(raan) * math.cos(inc), math.sin(inc))
    w = (math.sin(raan) * math.sin(inc), -math.cos(raan) * math.sin(inc), math.cos(inc))
    return p, q, w


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def shadow_arc(raan_deg: float, inclination_deg: float, alt_m: float,
               doy: float) -> tuple[float, float, float]:
    """``(beta_deg, centre_u_deg, half_width_deg)`` of the umbra arc.

    ``half_width_deg`` is 0 when |β| clears the umbra.
    """
    s = fe.sun_direction(doy)
    p, q, w = _plane_frame(raan_deg, inclination_deg)
    sin_b = max(-1.0, min(1.0, _dot(s, w)))
    beta = math.asin(sin_b)
    u_s = math.degrees(math.atan2(_dot(s, q), _dot(s, p)))
    r = RE_M + float(alt_m)
    c = math.sqrt(r * r - RE_M * RE_M) / (r * math.cos(beta)) if math.cos(beta) > 0 else 2.0
    half = math.degrees(math.acos(c)) if c < 1.0 else 0.0
    return math.degrees(beta), (u_s + 180.0) % 360.0, half


def sat_u_deg(sat: dict, t_s: float) -> float:
    n = fe.mean_motion_rad_s(float(sat["altitude_m"]))
    return (float(sat["phase_deg"]) + math.degrees(n * t_s)) % 360.0


def sat_state(sat: dict, doy: float, t_s: float) -> dict:
    """Lit flag plus time to the next umbra entry/exit [s] at instant ``t_s``.

    ``lit_left_s`` is the remaining sunlit time (∞ if the plane never enters
    the umbra); ``dark_left_s`` the remaining shadowed time (0 when lit);
    ``dark_total_s`` the full umbra duration per revolution.
    """
    _, centre, half = shadow_arc(sat["raan_deg"], sat["inclination_deg"],
                                 sat["altitude_m"], doy)
    n_deg_s = math.degrees(fe.mean_motion_rad_s(float(sat["altitude_m"])))
    if half <= 0.0:
        return {"lit": True, "lit_left_s": math.inf, "dark_left_s": 0.0, "dark_total_s": 0.0}
    u = sat_u_deg(sat, t_s)
    entry = (centre - half) % 360.0
    # angle travelled since the umbra entry point, in [0, 360)
    since_entry = (u - entry) % 360.0
    dark_total = 2.0 * half / n_deg_s
    if since_entry < 2.0 * half:
        return {"lit": False, "lit_left_s": 0.0,
                "dark_left_s": (2.0 * half - since_entry) / n_deg_s,
                "dark_total_s": dark_total}
    return {"lit": True, "lit_left_s": (360.0 - since_entry) / n_deg_s,
            "dark_left_s": 0.0, "dark_total_s": dark_total}


def fleet_states(sats: list[dict], doy: float, t_s: float) -> list[dict]:
    return [sat_state(s, doy, t_s) for s in sats]


def adjacency(sats: list[dict], edges: list[dict]) -> list[list[int]]:
    idx = {s["name"]: i for i, s in enumerate(sats)}
    adj: list[list[int]] = [[] for _ in sats]
    for e in edges:
        a, b = idx[e["a"]], idx[e["b"]]
        adj[a].append(b)
        adj[b].append(a)
    return adj


def escape_hops(adj: list[list[int]], lit: list[bool]) -> list[int | None]:
    """Hop distance to the nearest lit satellite (0 for lit ones).

    ``None`` when no lit satellite is reachable.
    """
    dist: list[int | None] = [None] * len(adj)
    dq: deque[int] = deque()
    for i, ok in enumerate(lit):
        if ok:
            dist[i] = 0
            dq.append(i)
    while dq:
        u = dq.popleft()
        for v in adj[u]:
            if dist[v] is None:
                dist[v] = dist[u] + 1
                dq.append(v)
    return dist


def capacitated_offload(adj: list[list[int]], lit: list[bool], k: int,
                        eligible: list[bool] | None = None) -> list[int | None]:
    """Hops each shadowed satellite travels when every lit receiver takes ≤ k.

    Shadowed satellites are served in order of their uncapacitated escape
    distance (closest to the terminator first), each by BFS to the nearest
    receiver with spare capacity. ``eligible`` optionally restricts receivers
    (e.g. lit satellites with enough lit time left). Returns one entry per
    shadowed satellite, ``None`` if it could not be placed.
    """
    recv = list(lit) if eligible is None else [a and b for a, b in zip(lit, eligible)]
    spare = [int(k) if r else 0 for r in recv]
    base = escape_hops(adj, recv)
    order = sorted((i for i, ok in enumerate(lit) if not ok),
                   key=lambda i: (math.inf if base[i] is None else base[i], i))
    out: list[int | None] = []
    for src in order:
        seen = {src}
        dq = deque([(src, 0)])
        got = None
        while dq:
            u, d = dq.popleft()
            if spare[u] > 0:
                spare[u] -= 1
                got = d
                break
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    dq.append((v, d + 1))
        out.append(got)
    return out


def kv_transfer_s(tokens: float, bytes_per_token: float, gbps: float,
                  hops: int, per_hop_stall_s: float = 0.0,
                  store_and_forward: bool = False) -> float:
    """KV move time over ``hops`` ISL hops [s].

    Default is pipelined (cut-through): one serialisation plus a per-hop
    stall. ``store_and_forward=True`` serialises once per hop, the
    pessimistic bound when relays must buffer the whole cache.
    """
    if hops <= 0:
        return 0.0
    ser = tokens * bytes_per_token * 8.0 / (gbps * 1e9)
    if store_and_forward:
        return hops * (ser + per_hop_stall_s)
    return ser + hops * per_hop_stall_s
