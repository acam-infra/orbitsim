"""Export co-simulation inputs: a viewer scenario + a contact trace for each built-in case.

The network simulator (satsim, ``satsim-cosim``) reads the trace; the playback page of the 3-D
viewer (viz/play.html) draws the satellites from the scenario with the same closed form, so the
network events and the orbits line up.

Usage:
  uv run python export_cosim.py                      # -> cosim_out/<case>.{scenario,trace}.json
  uv run python export_cosim.py <dir> [case,case]    # somewhere else / a subset

Cases:
  coop-w53   3 RS (RS-1030 / RS-1330 / RS-SAR) + Walker 53° 4×10 compute shell, 550 km.
             In-plane ring (36° apart; at 6×8 the 45° chord dips below RE+80 km) + cross-plane +Grid to the nearest satellite of the next
             plane, both while in range; each RS holds one sticky laser link to a compute satellite.
  coop-sso2  3 RS + 16 compute = 4 clusters × 4 on two SSO planes (LTAN 10:30 / 13:30, the SOW
             S-SSO2 layout); fixed links inside a cluster, cross-cluster only within 5000 km.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.dirname(__file__))

from orbitsim import contact_trace as ct
from orbitsim import fleet_synth as fs
import export_viz as ev
import research_sow_events as sow
import research_synth_fleet as syn

DOY = 81.0
HORIZON_S = 7200.0
DT_S = 5.0
RS_RANGE_M = syn.R_ISL            # 4000 km, as in research_synth_fleet
INTER_RANGE_M = 5000e3            # cross-plane / cross-cluster, as in research_sow_events
PLANES, SPP = 4, 10              # 36° in-plane spacing keeps the ring's line of sight above 80 km
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cosim_out")


def _rs():
    return [dict(s, group="rs", cluster=s["name"]) for s in syn.RS]


def case_w53():
    cs = [dict(s, group="compute", cluster=f"面{s['plane']}") for s in fs.walker("C", PLANES, SPP, 550, 53.0, F=1)]
    sats = _rs() + cs
    pairs = []
    intra_range = ct.chord_m(550e3, 360.0 / SPP) * 1.05
    for p in range(PLANES):
        names = [s["name"] for s in cs if s["plane"] == p]
        pairs += [(a, b, "intra", intra_range) for a, b in ct.ring_pairs(names)]
    pairs += [(a, b, "inter", INTER_RANGE_M) for a, b in ct.nearest_plane_pairs(cs, DOY)]
    attach = [ct.AttachRule("rs", "compute", "rs", RS_RANGE_M, "sticky")]
    title = "协同 · 3 颗遥感星 + Walker 53° 4×10 算力星座"
    desc = ("面内环 (相隔 36°) + 跨面 +Grid (≤ 5000 km 且视线高于地表 80 km 时在线); "
            "每颗遥感星一个激光终端, 保持当前算力星直到出视距 (≤ 4000 km) 再切换.")
    return "coop-w53", title, desc, sats, pairs, attach


def case_sso2():
    clusters = sow.build()["S-SSO2 (LTAN 10.5/13.5 ×2簇)"]
    cs = []
    for ci, c in enumerate(clusters):
        cs += [dict(s, group="compute", cluster=f"簇{ci}") for s in c]
    sats = _rs() + cs
    pairs = []
    for c in clusters:
        names = [s["name"] for s in c]
        pairs += [(a, b, "intra", 1000e3) for a, b in ct.ring_pairs(names, closed=False)]
    for i, a in enumerate(cs):
        for b in cs[i + 1:]:
            if a["cluster"] != b["cluster"]:
                pairs.append((a["name"], b["name"], "inter", INTER_RANGE_M))
    attach = [ct.AttachRule("rs", "compute", "rs", RS_RANGE_M, "sticky")]
    title = "协同 · 3 颗遥感星 + SOW S-SSO2 (4 簇 × 4 星)"
    desc = ("算力簇贴遥感星 LTAN (10:30 / 13:30); 簇内固定链路, 跨簇只在 ≤ 5000 km 时在线; "
            "遥感星一个激光终端 (≤ 4000 km).")
    return "coop-sso2", title, desc, sats, pairs, attach


CASES = {"coop-w53": case_w53, "coop-sso2": case_sso2}


def export_case(key: str, dst: str = OUT, horizon_s: float = HORIZON_S, dt_s: float = DT_S) -> dict:
    name, title, desc, sats, pairs, attach = CASES[key]()
    trace = ct.build_trace(sats, doy=DOY, horizon_s=horizon_s, dt_s=dt_s, pairs=pairs,
                           attach=attach, name=name)
    groups: dict[str, list] = {}
    for s in sats:
        groups.setdefault(s["group"], []).append((s["cluster"], [s]))
    scenario = ev.scenario(name, title, desc, DOY, list(groups.items()), [], [],
                           duration_h=horizon_s / 3600)
    # the trace and the scenario must index satellites identically
    assert [n["name"] for n in trace["nodes"]] == [s["name"] for s in scenario["satellites"]]
    os.makedirs(dst, exist_ok=True)
    for suffix, obj in (("scenario", scenario), ("trace", trace)):
        with open(os.path.join(dst, f"{name}.{suffix}.json"), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return trace


def main():
    dst = sys.argv[1] if len(sys.argv) > 1 else OUT
    keys = sys.argv[2].split(",") if len(sys.argv) > 2 else list(CASES)
    for k in keys:
        tr = export_case(k, dst)
        st = tr["stats"]
        print(f"{k}: {len(tr['nodes'])} nodes, {len(tr['edges'])} edges, "
              f"{st['topology_events']} events, compute dark {st.get('compute_dark_share', 0):.2f}, "
              f"rs handovers/h {st.get('rs_handovers_per_hour_per_sat', 0):.1f}")
        for kind, v in st["kinds"].items():
            fmt = lambda x: "-" if x is None else f"{x:.1f}"
            print(f"   {kind:6} edges={v['edges']:3d} contacts={v['contacts']:4d} "
                  f"p10/p50/p90 min={fmt(v['contact_min_p10'])}/{fmt(v['contact_min_p50'])}/"
                  f"{fmt(v['contact_min_p90'])} mean_up={v['mean_up_edges']:.1f}")
    print(f"-> {dst}")


if __name__ == "__main__":
    main()
