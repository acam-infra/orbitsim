"""Inter-satellite link (ISL) connectivity modes — the StarPerf idea, reduced
to closed-form circular-orbit geometry.

Each satellite gets an inertial position at t=0 from its orbital elements
(altitude, inclination, RAAN, in-plane phase). A *connection mode* then picks
edges. Modes are a closed set, mirroring StarPerf's ``connectivity_plugin``
folder:

- ``n_nearest``:     each satellite links its n nearest neighbours (within an
                     optional max range). Distance-search based, so an ideal
                     Walker δ at t=0 can hit exactly-coincident pairs (the
                     phase offset is a rational multiple of 360°); use
                     ``positive_grid`` when you want the topological +Grid.
- ``positive_grid``: topological +Grid — each satellite links its in-plane
                     predecessor/successor and the same-index satellite in the
                     two adjacent planes (2 intra + 2 inter, by construction).
                     This is the actual Starlink pattern and is immune to t=0
                     degeneracies. Requires a walker shell.
- ``ring``:          intra-orbit links only — each satellite links its two
                     in-plane neighbours; no inter-plane edges.
- ``bent_pipe``:     no ISLs at all (bent-pipe relay through the ground).

The snapshot is taken at t=0 (phases as declared); StarPerf makes the same
simplification ("ISL will not be disconnected and rebuilt once established").

Multi-shell constellations
--------------------------

A ``links:`` declaration can be either a single mode (applied per-shell, so
multi-shell constellations get intra-shell connectivity only) or a pair::

    links:
      intra_shell: {kind: positive_grid}                  # within each shell
      inter_shell: {kind: n_nearest, n: 2, max_range_km: 6000}  # across shells

Intra-shell modes: ``positive_grid`` / ``ring`` / ``n_nearest`` / ``bent_pipe``.
Inter-shell modes: ``n_nearest`` / ``bent_pipe`` (topological modes do not
generalise across shells — there is no well-defined "adjacent plane" between
shells at different altitudes).

Edge records: ``{a, b, distance_km, intra_plane, intra_shell}`` where
``a``/``b`` are satellite names. All distances in km.
"""

from __future__ import annotations

import math

from .constellation import Constellation, expand_satellites
from .orbit_sun import RE_M

# StarPerf's ISL_distance_range.xml default effective range [km].
DEFAULT_MAX_RANGE_KM = 6000.0

_INTRA_MODES = ("n_nearest", "positive_grid", "ring", "bent_pipe")
_INTER_MODES = ("n_nearest", "bent_pipe")


def _sat_position_eci(sat: dict) -> tuple[float, float, float]:
    """Inertial position [km] at t=0 for one expanded satellite record.

    Circular orbit: start in the orbital plane (phase measured from the
    ascending node), rotate by inclination about the line of nodes, then by
    RAAN about the z axis.
    """
    r = (RE_M + float(sat["altitude_m"])) / 1000.0  # km
    u = math.radians(float(sat["phase_deg"]))       # argument of latitude at t=0
    i = math.radians(float(sat["inclination_deg"]))
    raan = math.radians(float(sat.get("raan_deg", 0.0)))

    # position in the orbital plane
    x_p = r * math.cos(u)
    y_p = r * math.sin(u)
    # rotate about x-axis by inclination, then about z-axis by RAAN
    x1 = x_p
    y1 = y_p * math.cos(i)
    z1 = y_p * math.sin(i)
    x = x1 * math.cos(raan) - y1 * math.sin(raan)
    y = x1 * math.sin(raan) + y1 * math.cos(raan)
    z = z1
    return (x, y, z)


def _dist(p: tuple[float, float, float], q: tuple[float, float, float]) -> float:
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def _pairwise(sats: list[dict]) -> list[tuple[int, int, float]]:
    """All pairs with distances [km]: ``(i, j, d)`` with i < j."""
    pos = [_sat_position_eci(s) for s in sats]
    pairs = []
    for a in range(len(sats)):
        for b in range(a + 1, len(sats)):
            pairs.append((a, b, _dist(pos[a], pos[b])))
    return pairs


def _edges_n_nearest(sats: list[dict], n: int, max_range_km: float,
                     scope: str = "all") -> list[dict]:
    """Each satellite links its ``n`` nearest neighbours within ``max_range_km``.

    ``scope``: ``"all"`` considers every other satellite (used for both the
    whole-constellation single-mode case and the inter-shell case);
    ``"intra_shell"`` restricts candidates to the same shell.
    """
    pairs = _pairwise(sats)
    # adjacency: sat -> sorted list of (dist, other)
    adj: dict[int, list[tuple[float, int]]] = {i: [] for i in range(len(sats))}
    for a, b, d in pairs:
        if scope == "intra_shell" and sats[a]["shell"] != sats[b]["shell"]:
            continue
        if scope == "inter_shell" and sats[a]["shell"] == sats[b]["shell"]:
            continue
        if d <= max_range_km:
            adj[a].append((d, b))
            adj[b].append((d, a))
    chosen: set[tuple[int, int]] = set()
    for i, lst in adj.items():
        lst.sort()
        for d, j in lst[: int(n)]:
            chosen.add((min(i, j), max(i, j)))
    dmap = {(a, b): d for a, b, d in pairs}
    return [
        {
            "a": sats[a]["name"],
            "b": sats[b]["name"],
            "distance_km": dmap[(a, b)],
            "intra_plane": sats[a]["shell"] == sats[b]["shell"]
                           and sats[a]["plane"] == sats[b]["plane"],
            "intra_shell": sats[a]["shell"] == sats[b]["shell"],
        }
        for a, b in sorted(chosen)
    ]


def _edges_positive_grid(sats: list[dict], planes: int, spp: int) -> list[dict]:
    """Topological +Grid within one walker shell: each satellite links its
    in-plane predecessor/successor and the same-index satellite in the two
    adjacent planes (left/right).

    This is the actual Starlink pattern: 2 intra-plane + 2 inter-plane edges
    per satellite, by construction — not by distance search. StarPerf's
    distance-based ``n_nearest(n=4)`` converges to the same set on a healthy
    Walker shell, but a t=0 snapshot of an ideal Walker δ has exactly
    coincident pairs (the phase offset is a rational multiple of 360°), which
    breaks any nearest-neighbour search. The topological definition is immune
    to that.
    """
    pos = [_sat_position_eci(s) for s in sats]
    idx = {(int(s["plane"]), int(s["index_in_plane"])): i
           for i, s in enumerate(sats)}
    chosen: set[tuple[int, int]] = set()
    for s in sats:
        p, k = int(s["plane"]), int(s["index_in_plane"])
        # intra-plane: predecessor and successor along the orbit
        for k2 in ((k - 1) % spp, (k + 1) % spp):
            if k2 != k:
                j = idx[(p, k2)]
                chosen.add((min(idx[(p, k)], j), max(idx[(p, k)], j)))
        # inter-plane: same index in the two adjacent planes
        for p2 in ((p - 1) % planes, (p + 1) % planes):
            if p2 != p:
                j = idx[(p2, k)]
                chosen.add((min(idx[(p, k)], j), max(idx[(p, k)], j)))
    return [
        {
            "a": sats[a]["name"],
            "b": sats[b]["name"],
            "distance_km": _dist(pos[a], pos[b]),
            "intra_plane": sats[a]["plane"] == sats[b]["plane"],
            "intra_shell": True,
        }
        for a, b in sorted(chosen)
    ]


def _edges_ring(sats: list[dict]) -> list[dict]:
    """Intra-orbit ring: each satellite links its two in-plane neighbours."""
    pos = [_sat_position_eci(s) for s in sats]
    edges = []
    planes: dict[tuple[str, int], list[int]] = {}
    for i, s in enumerate(sats):
        planes.setdefault((s["shell"], int(s["plane"])), []).append(i)
    for members in planes.values():
        members.sort(key=lambda i: float(sats[i]["phase_deg"]))
        m = len(members)
        for k in range(m):
            a, b = members[k], members[(k + 1) % m]
            if a == b:
                continue
            lo, hi = min(a, b), max(a, b)
            edges.append({
                "a": sats[lo]["name"],
                "b": sats[hi]["name"],
                "distance_km": _dist(pos[lo], pos[hi]),
                "intra_plane": True,
                "intra_shell": True,
            })
    # de-duplicate (single-sat plane would self-loop; two-sat plane adds one edge twice)
    seen = set()
    out = []
    for e in edges:
        key = (e["a"], e["b"])
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def _build_intra_shell_edges(const: Constellation, mode: dict,
                             sats: list[dict]) -> list[dict]:
    """Apply one intra-shell mode to every shell separately and concatenate."""
    kind = mode.get("kind")
    if kind not in _INTRA_MODES:
        raise ValueError(f"intra_shell.kind must be one of {_INTRA_MODES}, got {kind!r}")
    if kind == "bent_pipe":
        return []
    max_range = float(mode.get("max_range_km", DEFAULT_MAX_RANGE_KM))
    edges: list[dict] = []
    for shell in const.shells:
        shell_sats = [s for s in sats if s["shell"] == shell.name]
        if kind == "n_nearest":
            edges.extend(_edges_n_nearest(shell_sats, int(mode.get("n", 4)),
                                          max_range, scope="all"))
        elif kind == "positive_grid":
            if shell.kind != "walker":
                raise ValueError(
                    f"positive_grid requires a walker shell, got {shell.kind!r} "
                    f"(shell {shell.name!r})")
            edges.extend(_edges_positive_grid(
                shell_sats,
                int(shell.params["planes"]),
                int(shell.params["sats_per_plane"]),
            ))
        elif kind == "ring":
            edges.extend(_edges_ring(shell_sats))
    return edges


def build_edges(const: Constellation, mode: dict) -> list[dict]:
    """Dispatch a ``links:`` declaration into an edge list.

    Accepts either a single-mode mapping (applied per-shell for multi-shell
    constellations — no cross-shell edges) or a ``{intra_shell, inter_shell}``
    pair. ``inter_shell`` defaults to ``bent_pipe`` when omitted.
    """
    sats = expand_satellites(const)

    # paired declaration: intra_shell + inter_shell
    if "intra_shell" in mode or "inter_shell" in mode:
        intra_mode = dict(mode.get("intra_shell", {"kind": "bent_pipe"}))
        inter_mode = dict(mode.get("inter_shell", {"kind": "bent_pipe"}))
        intra_edges = _build_intra_shell_edges(const, intra_mode, sats)
        inter_kind = inter_mode.get("kind")
        if inter_kind not in _INTER_MODES:
            raise ValueError(
                f"inter_shell.kind must be one of {_INTER_MODES}, got {inter_kind!r}")
        if inter_kind == "bent_pipe" or const.n_shells == 1:
            inter_edges: list[dict] = []
        else:
            inter_edges = _edges_n_nearest(
                sats, int(inter_mode.get("n", 2)),
                float(inter_mode.get("max_range_km", DEFAULT_MAX_RANGE_KM)),
                scope="inter_shell",
            )
        return intra_edges + inter_edges

    # single-mode sugar
    kind = mode.get("kind")
    if kind not in _INTRA_MODES:
        raise ValueError(f"links.kind must be one of {_INTRA_MODES}, got {kind!r}")
    return _build_intra_shell_edges(const, mode, sats)


def summarize_edges(const: Constellation, edges: list[dict]) -> dict[str, float]:
    """Headline ISL statistics: counts, degree distribution, intra/inter split
    (both per-plane and per-shell)."""
    sats = expand_satellites(const)
    degree: dict[str, int] = {s["name"]: 0 for s in sats}
    for e in edges:
        degree[e["a"]] += 1
        degree[e["b"]] += 1
    degs = sorted(degree.values())
    intra_plane = sum(1 for e in edges if e["intra_plane"])
    intra_shell = sum(1 for e in edges if e.get("intra_shell", True))
    dists = [e["distance_km"] for e in edges]
    return {
        "n_shells": const.n_shells,
        "n_sats": len(sats),
        "n_edges": len(edges),
        "intra_plane_edges": intra_plane,
        "inter_plane_edges": len(edges) - intra_plane,
        "intra_shell_edges": intra_shell,
        "inter_shell_edges": len(edges) - intra_shell,
        "degree_min": degs[0] if degs else 0,
        "degree_max": degs[-1] if degs else 0,
        "degree_mean": (sum(degs) / len(degs)) if degs else 0.0,
        "link_km_min": min(dists) if dists else 0.0,
        "link_km_max": max(dists) if dists else 0.0,
        "link_km_mean": (sum(dists) / len(dists)) if dists else 0.0,
    }
