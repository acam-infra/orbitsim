"""Time-varying contact trace for a mixed fleet: the geometry a network simulator consumes.

``fleet_synth`` answers "what does the fleet look like at time t". A discrete-event network
simulator (satsim) instead needs the *events*: when each link comes up and goes down, and when
each satellite enters and leaves the umbra. This module samples the closed-form propagation on a
fixed grid and turns the masks into intervals.

Link candidates are declared, not inferred, because which pairs carry a terminal is a design
choice, not geometry:

``pairs``  explicit candidate pairs ``(a, b, kind, max_range_m)``; up while in range and the
           segment clears ``RE + grazing_m`` (e.g. in-plane neighbours, cross-plane grid links).
``attach`` one-terminal rules, e.g. a remote-sensing (RS) satellite with one laser terminal
           that keeps its compute partner until the partner leaves range (``sticky``) or always
           jumps to the nearest (``nearest``). These produce the RS→compute handovers.

The output is plain JSON-able data (see ``build_trace``). Times are seconds after 00:00 UTC of
day ``doy`` — the same clock as ``export_viz`` scenarios, so a playback viewer can draw the
satellites with its own propagator and stay aligned with the trace.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import fleet_synth as fs


@dataclass(frozen=True)
class AttachRule:
    """Each satellite of group ``a`` holds at most one link to a satellite of group ``b``."""

    a: str
    b: str
    kind: str = "rs"
    max_range_m: float = 4000e3
    policy: str = "sticky"  # sticky | nearest
    require_lit_b: bool = False


def intervals(mask: np.ndarray, t: np.ndarray, dt: float) -> list[list[float]]:
    """[start, end) runs of True in a 1-D mask sampled at ``t`` (end clipped to the horizon)."""
    m = np.r_[False, np.asarray(mask, bool), False].astype(np.int8)
    d = np.diff(m)
    up = np.where(d == 1)[0]
    down = np.where(d == -1)[0]
    horizon = float(t[-1] + dt)
    out = []
    for i, j in zip(up, down):
        t1 = float(t[j]) if j < len(t) else horizon
        out.append([float(t[i]), t1])
    return out


def _group(s: dict) -> str:
    return str(s.get("group", s["role"]))


def pair_masks(pos: np.ndarray, idx_a: np.ndarray, idx_b: np.ndarray, max_range_m: np.ndarray,
               grazing_m: float) -> np.ndarray:
    """Up-mask (T, P) for P candidate pairs."""
    pa = pos[:, idx_a, :]
    pb = pos[:, idx_b, :]
    d = pb - pa
    L2 = np.einsum("tpk,tpk->tp", d, d)
    s = np.clip(-np.einsum("tpk,tpk->tp", pa, d) / np.maximum(L2, 1.0), 0.0, 1.0)
    c = pa + s[..., None] * d
    clear = np.einsum("tpk,tpk->tp", c, c) > (fs.RE_M + grazing_m) ** 2
    return clear & (np.sqrt(L2) <= max_range_m[None, :])


def attach_masks(pos: np.ndarray, lit: np.ndarray, sats: list[dict], rule: AttachRule,
                 grazing_m: float) -> dict[tuple[int, int], np.ndarray]:
    """Per (a, b) pair, the steps on which a's single terminal points at b."""
    A = [i for i, s in enumerate(sats) if _group(s) == rule.a]
    B = np.array([j for j, s in enumerate(sats) if _group(s) == rule.b])
    T = pos.shape[0]
    out: dict[tuple[int, int], np.ndarray] = {}
    for i in A:
        rng, clear = fs.los_range(pos[:, [i], :], pos[:, B, :], grazing_m)
        ok = clear[:, 0, :] & (rng[:, 0, :] <= rule.max_range_m)
        if rule.require_lit_b:
            ok &= lit[:, B]
        r = np.where(ok, rng[:, 0, :], np.inf)
        cur = -1
        for k in range(T):
            if rule.policy == "sticky" and cur >= 0 and ok[k, cur]:
                pass
            else:
                cur = int(np.argmin(r[k])) if np.isfinite(r[k]).any() else -1
            if cur >= 0:
                key = (i, int(B[cur]))
                if key not in out:
                    out[key] = np.zeros(T, bool)
                out[key][k] = True
    return out


def build_trace(sats: list[dict], *, doy: float, horizon_s: float, dt_s: float = 5.0,
                pairs: list[tuple[str, str, str, float]] = (), attach: list[AttachRule] = (),
                grazing_m: float = 80e3, name: str = "trace") -> dict:
    """Sample the fleet and return the event trace.

    Returns ``{"nodes", "edges", "dark", "stats", ...}`` where
      nodes  ``[{id, name, role, group, cluster}]``  (id = index into ``sats``)
      edges  ``[{u, v, kind, up: [[t0, t1), ...]}]`` with u < v, only pairs that are ever up
      dark   per node, umbra intervals ``[[t0, t1), ...]``
    """
    t = np.arange(0.0, float(horizon_s), float(dt_s))
    pos = fs.positions(sats, doy, t)
    lit = fs.lit(pos, fs.sun_vec(doy))
    name_idx = {s["name"]: i for i, s in enumerate(sats)}

    masks: dict[tuple[int, int], tuple[str, np.ndarray]] = {}
    if pairs:
        ia = np.array([name_idx[a] for a, _, _, _ in pairs])
        ib = np.array([name_idx[b] for _, b, _, _ in pairs])
        mr = np.array([float(r) for *_, r in pairs])
        pm = pair_masks(pos, ia, ib, mr, grazing_m)
        for p, (a, b, kind, _) in enumerate(pairs):
            u, v = sorted((name_idx[a], name_idx[b]))
            masks[(u, v)] = (kind, pm[:, p])
    for rule in attach:
        for (i, j), m in attach_masks(pos, lit, sats, rule, grazing_m).items():
            u, v = sorted((i, j))
            if (u, v) in masks:
                kind, old = masks[(u, v)]
                masks[(u, v)] = (kind, old | m)
            else:
                masks[(u, v)] = (rule.kind, m)

    edges = []
    for (u, v), (kind, m) in sorted(masks.items()):
        iv = intervals(m, t, dt_s)
        if iv:
            edges.append({"u": u, "v": v, "kind": kind, "up": iv})
    dark = [intervals(~lit[:, j], t, dt_s) for j in range(len(sats))]
    nodes = [{"id": i, "name": s["name"], "role": s["role"], "group": _group(s),
              "cluster": str(s.get("cluster", s.get("plane", s["role"])))}
             for i, s in enumerate(sats)]
    return {
        "schema": "orbitsim.contact_trace/v1",
        "name": name,
        "epoch_doy": float(doy),
        "horizon_s": float(t[-1] + dt_s),
        "dt_s": float(dt_s),
        "nodes": nodes,
        "edges": edges,
        "dark": dark,
        "stats": trace_stats(nodes, edges, dark, float(t[-1] + dt_s)),
    }


def _pct(xs: list[float], q: float) -> float | None:
    return float(np.percentile(xs, q)) if xs else None


def trace_stats(nodes: list[dict], edges: list[dict], dark: list[list], horizon: float) -> dict:
    """Per link kind: contact durations (closed intervals only) and availability; umbra share."""
    out: dict = {"kinds": {}}
    for kind in sorted({e["kind"] for e in edges}):
        es = [e for e in edges if e["kind"] == kind]
        closed = [b - a for e in es for a, b in e["up"] if a > 0 and b < horizon]
        up = sum(b - a for e in es for a, b in e["up"])
        out["kinds"][kind] = {
            "edges": len(es),
            "contacts": sum(len(e["up"]) for e in es),
            "contact_min_p10": None if not closed else _pct(closed, 10) / 60,
            "contact_min_p50": None if not closed else _pct(closed, 50) / 60,
            "contact_min_p90": None if not closed else _pct(closed, 90) / 60,
            "mean_up_edges": up / horizon,
        }
    # handovers per hour of one-terminal (rs) satellites: count of link starts after t=0
    rs_ids = {n["id"] for n in nodes if n["role"] == "rs"}
    if rs_ids:
        starts = sum(1 for e in edges if e["kind"] == "rs" for a, _ in e["up"] if a > 0)
        out["rs_handovers_per_hour_per_sat"] = starts / len(rs_ids) / (horizon / 3600)
    comp = [n["id"] for n in nodes if n["role"] != "rs"]
    if comp:
        out["compute_dark_share"] = sum(b - a for j in comp for a, b in dark[j]) / (len(comp) * horizon)
    out["topology_events"] = sum(2 * len(e["up"]) for e in edges) + sum(2 * len(d) for d in dark)
    return out


def nearest_plane_pairs(sats: list[dict], doy: float, plane_key: str = "plane") -> list[tuple[str, str]]:
    """+Grid cross-plane candidates: each satellite to its nearest one in the next plane at t=0."""
    planes: dict[int, list[int]] = {}
    for i, s in enumerate(sats):
        planes.setdefault(int(s[plane_key]), []).append(i)
    ps = sorted(planes)
    pos = fs.positions(sats, doy, np.array([0.0]))[0]
    out = []
    for k, p in enumerate(ps):
        q = ps[(k + 1) % len(ps)]
        if q == p:
            continue
        for i in planes[p]:
            j = min(planes[q], key=lambda j: float(np.linalg.norm(pos[j] - pos[i])))
            out.append((sats[i]["name"], sats[j]["name"]))
    return out


def ring_pairs(names: list[str], closed: bool = True) -> list[tuple[str, str]]:
    out = list(zip(names, names[1:]))
    if closed and len(names) > 2:
        out.append((names[-1], names[0]))
    return out


def chord_m(alt_m: float, du_deg: float) -> float:
    """Straight-line distance between two satellites ``du`` apart on one circular orbit."""
    return 2 * (fs.RE_M + alt_m) * math.sin(math.radians(du_deg) / 2)
