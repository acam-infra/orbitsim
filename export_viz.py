"""Export orbitsim scenarios as JSON for the 3-D viewer in ``viz/`` (see viz/README.md).

The viewer re-propagates with the same closed form as ``fleet_synth``:
  RAAN(t) = raan0 + rate·t,  u(t) = u0 + n·t,  ECEF = Rz(−θ_G)·ECI,
  θ_G = α_sun(doy) + π + 2π·t/86400   (t = UTC seconds since 00:00 of the epoch day)
and the same mean-Sun umbra test. ``check`` carries reference ECEF positions and lit flags
so the viewer's test suite can hold the TypeScript port to this file.

Usage:
  uv run python export_viz.py                 # built-in scenarios -> viz/public/scenarios
  uv run python export_viz.py <dir>           # somewhere else

From your own script (any list of ``fleet_synth.make_sat`` / ``walker`` / ``sso_plane`` records):

  from export_viz import export_scenario
  export_scenario("my-case", "标题", sats, links=[["a", "b", "inter"]], doy=172)
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.dirname(__file__))

from orbitsim import fleet_energy as fe
from orbitsim import fleet_synth as fs
import research_sow_events as sow
import research_synth_fleet as syn

YEAR = 2026
STATIONS = [{"name": n, "lat": a, "lon": b} for n, (a, b) in syn.STATIONS_PLUS.items()]


def sat_record(s: dict, doy: float, group: str, cluster: str | None = None) -> dict:
    alpha = fs.sun_ra_rad(doy)
    raan0 = (alpha + math.radians((s["ltan_h"] - 12.0) * 15.0)) if s["ltan_h"] is not None \
        else math.radians(s["raan_deg"])
    return {
        "name": s["name"], "role": s["role"], "group": group, "cluster": cluster or group,
        "alt_m": s["alt_m"], "inc_deg": s["inc_deg"],
        "raan0_deg": math.degrees(raan0) % 360.0,
        "raan_rate_deg_s": math.degrees(fs.raan_rate_rad_s(s["alt_m"], s["inc_deg"])),
        "u0_deg": s["u0_deg"] % 360.0,
        "n_deg_s": math.degrees(fe.mean_motion_rad_s(s["alt_m"])),
        "ltan_h": s["ltan_h"],
    }


def chain(names: list[str], kind: str, closed: bool = False) -> list[list[str]]:
    out = [[a, b, kind] for a, b in zip(names, names[1:])]
    if closed and len(names) > 2:
        out.append([names[-1], names[0], kind])
    return out


def ecef(pos: np.ndarray, doy: float, t: np.ndarray) -> np.ndarray:
    th = fs.gmst_rad(doy, t)[:, None]
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    return np.stack([x * np.cos(th) + y * np.sin(th), -x * np.sin(th) + y * np.cos(th), z], axis=-1)


def check_samples(sats: list[dict], doy: float) -> list[dict]:
    t = np.array([0.0, 1234.0, 5000.0, 43210.0])
    pos = fs.positions(sats, doy, t)
    pe = ecef(pos, doy, t)
    lit = fs.lit(pos, fs.sun_vec(doy))
    out = []
    for j in range(0, len(sats), max(1, len(sats) // 6)):
        for i, tt in enumerate(t):
            out.append({"sat": sats[j]["name"], "t": float(tt),
                        "ecef": [float(v) for v in pe[i, j]], "lit": bool(lit[i, j])})
    return out


def scenario(name, title, desc, doy, groups, static, dynamic, stations=True, duration_h=6):
    sats_raw, recs = [], []
    for gname, members in groups:
        for cname, ss in members:
            for s in ss:
                sats_raw.append(s)
                recs.append(sat_record(s, doy, gname, cname))
    epoch = dt.datetime(YEAR, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=int(doy))
    return {
        "name": name, "title": title, "description": desc,
        "epoch_doy": doy, "epoch_iso": epoch.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_s": duration_h * 3600,
        "satellites": recs,
        "links": {"static": static, "dynamic": dynamic},
        "stations": STATIONS if stations else [],
        "check": check_samples(sats_raw, doy),
    }


def sow_scenarios(doy=81.0):
    cfgs = sow.build()
    out = []
    keys = {"S-SSO4 (LTAN 0/6/12/18)": ("sow-sso4", "SOW · S-SSO4 四个 SSO 面各 1 簇"),
            "S-SSO2 (LTAN 10.5/13.5 ×2簇)": ("sow-sso2", "SOW · S-SSO2 两个 SSO 面、每面两簇 (相隔 180°)"),
            "S-W53 (53° RAAN 均布)": ("sow-w53", "SOW · S-W53 四个 53° 面各 1 簇")}
    for label, clusters in cfgs.items():
        name, title = keys[label]
        members = [(f"簇{ci}", c) for ci, c in enumerate(clusters)]
        static = []
        for c in clusters:
            static += chain([s["name"] for s in c], "intra")
        out.append(scenario(
            name, title,
            "16 星 = 4 簇 × 4 星, 550 km, 簇内间隔 2°. 簇内固定链路 (25 Gbps); "
            "跨簇只在 ≤5000 km 且视线高于地表 80 km 时连线.",
            doy, [("compute", members)], static,
            [{"a": "compute", "b": "compute", "kind": "inter", "max_range_m": 5000e3,
              "grazing_m": 80e3, "different_cluster": True}]))
    # 同面接力: 一个 SSO 面 (LTAN 10.5), 每 40° 一簇, 9 簇 × 2 星
    relay = [sow.cluster(f"r{c}", 2, ltan=10.5, u0=40.0 * c) for c in range(9)]
    static = []
    for c in relay:
        static += chain([s["name"] for s in c], "intra")
    static += chain([c[0]["name"] for c in relay], "inter", closed=True)
    out.append(scenario(
        "sow-relay", "SOW · 同面接力: 一个 SSO 面每 40° 一簇 (9 簇 × 2 星)",
        "相邻簇相隔 40° (≈4800 km), 前簇进影时后簇还有 ≈10.6 min 光照, 一跳可达.",
        doy, [("compute", [(f"簇{ci}", c) for ci, c in enumerate(relay)])], static, []))
    return out


def synth_scenarios(doy=81.0):
    rs = [(s["name"], [s]) for s in syn.RS]
    out = []
    for key, name, title in (("C3 Walker53 6x8", "synth-w53", "合成 · 3 颗遥感星 + Walker 53° 6×8 算力星座"),
                             ("C2 晨昏面12", "synth-dawn-dusk", "合成 · 3 颗遥感星 + 晨昏面 12 星"),
                             ("C1 同面伴飞6", "synth-coplanar", "合成 · 3 颗遥感星 + 与 RS-1030 同面伴飞 6 星")):
        cs = syn.COMPUTE[key]
        planes: dict[int, list[dict]] = {}
        for s in cs:
            planes.setdefault(s.get("plane", 0), []).append(s)
        static = []
        for p, ss in planes.items():
            static += chain([s["name"] for s in ss], "intra", closed=len(ss) > 2)
        if len(planes) > 1:
            # +Grid across planes: each satellite to the nearest one of the next plane at the
            # epoch. Same-index pairing is 60° apart in u for a 6-plane F=1 shell (> 6000 km).
            ps = sorted(planes)
            pos = fs.positions(cs, doy, np.array([0.0]))[0]
            row = {s["name"]: i for i, s in enumerate(cs)}
            for i, p in enumerate(ps):
                q = ps[(i + 1) % len(ps)]
                for a in planes[p]:
                    pa = pos[row[a["name"]]]
                    b = min(planes[q], key=lambda s: float(np.linalg.norm(pos[row[s["name"]]] - pa)))
                    static.append([a["name"], b["name"], "inter"])
        out.append(scenario(
            name, title,
            "遥感星连最近一颗视距内 (≤4000 km) 且在光照中的算力星; 算力星座内部为 +Grid / 环.",
            doy, [("rs", rs), ("compute", [(key, cs)])], static,
            [{"a": "rs", "b": "compute", "kind": "rs", "max_range_m": syn.R_ISL,
              "grazing_m": 80e3, "nearest_only": True, "require_lit_b": True}]))
    return out


DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viz", "public", "scenarios")


def write_scenario(sc: dict, dst: str = DEFAULT_DIR) -> str:
    """Write one scenario JSON and add (or replace) its entry in ``index.json``."""
    os.makedirs(dst, exist_ok=True)
    path = os.path.join(dst, f"{sc['name']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sc, f, ensure_ascii=False, indent=1)
    idx_path = os.path.join(dst, "index.json")
    index = []
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as f:
            index = [e for e in json.load(f) if e["name"] != sc["name"]]
    index.append({"name": sc["name"], "title": sc["title"], "satellites": len(sc["satellites"])})
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    return path


def export_scenario(name: str, title: str, sats: list[dict], *, links=None, dynamic=None,
                    doy: float = 81.0, description: str = "", stations: bool = True,
                    duration_h: float = 6, dst: str = DEFAULT_DIR) -> str:
    """Export ``fleet_synth`` satellite records as a viewer scenario; returns the JSON path.

    ``sats``      records from ``fleet_synth.make_sat`` / ``walker`` / ``sso_plane``. A record's
                  ``cluster`` key (else its ``plane``) sets its colour; ``role="rs"`` draws it as a
                  remote-sensing satellite.
    ``links``     static links ``[[name_a, name_b, kind], ...]``; kind is ``intra`` (cyan),
                  ``inter`` (yellow) or ``rs`` (red).
    ``dynamic``   link rules re-evaluated every frame, e.g.
                  ``{"a": "rs", "b": "compute", "kind": "rs", "max_range_m": 4e6,
                  "grazing_m": 8e4, "nearest_only": True, "require_lit_b": True}``;
                  ``a`` / ``b`` name groups (a record's ``group`` key, else its ``role``).
    ``doy``       day of year the scenario opens on (0 = 1 Jan); the viewer's slider moves it.
    """
    members = []
    for s in sats:
        cluster = str(s.get("cluster", s.get("plane", s["role"])))
        members.append((s.get("group", s["role"]), cluster, s))
    groups: dict[str, list] = {}
    for g, c, s in members:
        groups.setdefault(g, []).append((c, [s]))
    sc = scenario(name, title, description, doy, list(groups.items()), links or [], dynamic or [],
                  stations=stations, duration_h=duration_h)
    return write_scenario(sc, dst)


def main():
    dst = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    for sc in sow_scenarios() + synth_scenarios():
        write_scenario(sc, dst)
        print(f"{sc['name']:>16}: {len(sc['satellites'])} sats, {len(sc['links']['static'])} static links")
    print(f"-> {dst}")


if __name__ == "__main__":
    main()
