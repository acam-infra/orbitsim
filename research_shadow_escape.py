"""地影逃逸: 迁移判据的几何输入.

接 handoff-satellite-3claims §3 原因 2 ("地影在相邻轨道面之间几乎同相, 要逃出去得跨 3-4 个面")
和 lit_synthesis §2 ("停机能预知时, 迁移/等待判据可写成闭式").

问题:
  Q1 进影星到最近亮星要几跳 (+Grid, 无容量限制)?  与面数、相位因子 F 的关系?
  Q2 每颗亮星最多接 k 颗影星的负载时, 要几跳? 有没有接不下的?
  Q3 请求寿命 L 的长任务, 到达时能否就近找到"剩余光照 ≥ L"的星 (星历放置)?
     找得到, 地影就不需要运行中迁移 —— 这是审稿人会拿来推翻 C2 的基线.
  Q4 迁移 vs 等待: KV 搬运时间 vs 剩余影时, 闭式比值.

几何: 圆轨道/球形地球/圆柱地影, 影弧闭式 (shadow_escape.shadow_arc), 与 lit_mask 逐点一致.
"""
from __future__ import annotations

import csv
import math
import os
import statistics as stats
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from orbitsim import orbit_sun as osun
from orbitsim import shadow_escape as se
from orbitsim.constellation import from_walker, expand_satellites
from orbitsim.isl import build_edges

OUT = os.path.join(os.path.dirname(__file__), "research_out")
os.makedirs(OUT, exist_ok=True)

DAYS = [float(d) for d in range(0, 365, 15)]   # 25 天, 覆盖季节
N_T = 48                                          # 每天 48 个时刻
LIFE_MIN = [5, 10, 20, 40]                        # 请求寿命 (min); LAB-1687 长任务 6k-18k tok × ~30 ms ≈ 3-9 min
KVB = 131072                                      # Llama-3.1-8B GQA, B/token (同 LAB-1687 sim.py)

SSO550 = osun.sso_inclination_deg(550e3)
CONFIGS = [
    # (label, planes, spp, alt, inc, F)
    ("4x4 F1 SSO (LAB-1687 规模)", 4, 4, 550e3, SSO550, 1),
    ("6x8 F1 SSO", 6, 8, 550e3, SSO550, 1),
    ("6x8 F3 SSO", 6, 8, 550e3, SSO550, 3),
    ("12x12 F1 SSO", 12, 12, 550e3, SSO550, 1),
    ("12x12 F5 SSO", 12, 12, 550e3, SSO550, 5),
    ("6x8 F1 53deg", 6, 8, 550e3, 53.0, 1),
    ("12x12 F1 53deg", 12, 12, 550e3, 53.0, 1),
    ("24x22 F1 53deg (Starlink 壳 1/3)", 24, 22, 550e3, 53.0, 1),
]


def bfs_to(adj, src, ok):
    """Hops from src to the nearest node with ok[node]; None if unreachable."""
    if ok[src]:
        return 0
    seen = {src}
    frontier = [src]
    d = 0
    while frontier:
        d += 1
        nxt = []
        for u in frontier:
            for v in adj[u]:
                if v not in seen:
                    if ok[v]:
                        return d
                    seen.add(v)
                    nxt.append(v)
        frontier = nxt
    return None


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def frac_le(xs, h):
    return sum(1 for x in xs if x is not None and x <= h) / len(xs) if xs else float("nan")


def run_config(label, planes, spp, alt, inc, F):
    const = from_walker(planes, spp, alt, inc, F)
    sats = expand_satellites(const)
    adj = se.adjacency(sats, build_edges(const, {"kind": "positive_grid"}))
    n = len(sats)
    period = 2 * math.pi / se.fe.mean_motion_rad_s(alt)

    shadow_frac, esc, cap1, cap1_fail, dark_left = [], [], [], 0, []
    neigh_dark = []           # 影星的 +Grid 邻居里也在影的比例
    plane_nb_dark = []        # 影星的相邻面同号邻居也在影的比例
    place = {L: [] for L in LIFE_MIN}  # 任一到达星 → 最近 lit_left ≥ L 的星的跳数
    n_shadow_total = 0
    for doy in DAYS:
        for k in range(N_T):
            t = 86400.0 * k / N_T
            st = se.fleet_states(sats, doy, t)
            lit = [s["lit"] for s in st]
            shadow_frac.append(1 - sum(lit) / n)
            hops = se.escape_hops(adj, lit)
            sh = [i for i in range(n) if not lit[i]]
            n_shadow_total += len(sh)
            for i in sh:
                esc.append(hops[i])
                dark_left.append(st[i]["dark_left_s"])
                nb = adj[i]
                neigh_dark.append(sum(1 for v in nb if not lit[v]) / len(nb))
                pnb = [v for v in nb if sats[v]["plane"] != sats[i]["plane"]]
                if pnb:
                    plane_nb_dark.append(sum(1 for v in pnb if not lit[v]) / len(pnb))
            c = se.capacitated_offload(adj, lit, k=1)
            cap1.extend(x for x in c if x is not None)
            cap1_fail += sum(1 for x in c if x is None)
            for L in LIFE_MIN:
                ok = [s["lit_left_s"] >= 60.0 * L for s in st]
                # 均匀抽 16 个到达星, 控制计算量
                for src in range(0, n, max(1, n // 16)):
                    place[L].append(bfs_to(adj, src, ok))

    esc_ok = [h for h in esc if h is not None]
    row = {
        "config": label, "sats": n, "period_min": period / 60,
        "shadow_frac_mean": stats.mean(shadow_frac),
        "esc_p1": frac_le(esc, 1), "esc_p2": frac_le(esc, 2),
        "esc_p50": pct(esc_ok, 0.5) if esc_ok else None,
        "esc_max": max(esc_ok) if esc_ok else None,
        "nb_dark_mean": stats.mean(neigh_dark) if neigh_dark else 0.0,
        "plane_nb_dark_mean": stats.mean(plane_nb_dark) if plane_nb_dark else 0.0,
        "cap1_mean": stats.mean(cap1) if cap1 else None,
        "cap1_p90": pct(cap1, 0.9) if cap1 else None,
        "cap1_max": max(cap1) if cap1 else None,
        "cap1_fail": cap1_fail / n_shadow_total if n_shadow_total else 0.0,
        "dark_left_mean_min": stats.mean(dark_left) / 60 if dark_left else 0.0,
    }
    for L in LIFE_MIN:
        row[f"place{L}_h0"] = frac_le(place[L], 0)
        row[f"place{L}_h1"] = frac_le(place[L], 1)
        row[f"place{L}_h2"] = frac_le(place[L], 2)
        row[f"place{L}_none"] = sum(1 for x in place[L] if x is None) / len(place[L])
    return row, esc, cap1


def migrate_vs_wait():
    """Q4: KV 搬运时间 / 剩余影时. 用 LAB-1687 长任务中途的 context 量级."""
    rows = []
    for ctx in (4096, 12288, 30000):
        for gbps in (10.0, 4.0, 1.0):   # 10: LAB-1687 cross; 4: 扣掉 6 Gbps 背景数传; 1: 拥塞
            for hops in (1, 2, 4):
                t = se.kv_transfer_s(ctx, KVB, gbps, hops, per_hop_stall_s=0.05)
                rows.append({"ctx_tok": ctx, "gbps": gbps, "hops": hops,
                             "kv_GB": ctx * KVB / 1e9, "kv_s": t})
    return rows


def main():
    rows, hists = [], {}
    for cfg in CONFIGS:
        print(f"扫 {cfg[0]} ...", flush=True)
        r, esc, cap1 = run_config(*cfg)
        rows.append(r)
        hists[cfg[0]] = (esc, cap1)

    keys = list(rows[0].keys())
    with open(os.path.join(OUT, "shadow_escape.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})

    print("\nQ1/Q2 逃逸跳数")
    print(f"{'config':>34} {'影比':>5} {'1跳':>5} {'≤2跳':>5} {'max':>4} {'邻居同影':>7} {'邻面同影':>7} "
          f"{'k=1均':>6} {'k=1 p90':>7} {'k=1max':>6} {'接不下':>6} {'剩余影min':>8}")
    for r in rows:
        print(f"{r['config']:>34} {r['shadow_frac_mean']:5.2f} {r['esc_p1']:5.2f} {r['esc_p2']:5.2f} "
              f"{str(r['esc_max']):>4} {r['nb_dark_mean']:7.2f} {r['plane_nb_dark_mean']:7.2f} "
              f"{(r['cap1_mean'] or 0):6.2f} {str(r['cap1_p90']):>7} {str(r['cap1_max']):>6} "
              f"{r['cap1_fail']:6.2f} {r['dark_left_mean_min']:8.1f}")

    print("\nQ3 星历放置: 到达时 0/1/2 跳内有'剩余光照 ≥ L'的星的比例")
    print(f"{'config':>34} " + " ".join(f"{'L=' + str(L) + 'm h0/h1/h2':>18}" for L in LIFE_MIN))
    for r in rows:
        cells = [f"{r[f'place{L}_h0']:.2f}/{r[f'place{L}_h1']:.2f}/{r[f'place{L}_h2']:.2f}" for L in LIFE_MIN]
        print(f"{r['config']:>34} " + " ".join(f"{c:>18}" for c in cells))

    mv = migrate_vs_wait()
    with open(os.path.join(OUT, "migrate_vs_wait.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(mv[0].keys()))
        w.writeheader()
        for r in mv:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    print("\nQ4 KV 搬运时间 [s] (pipelined, 每跳 50 ms stall)")
    for r in mv:
        if r["hops"] == 2:
            print(f"  ctx={r['ctx_tok']:>6} tok ({r['kv_GB']:.2f} GB) @ {r['gbps']:>4} Gbps, 2 跳: {r['kv_s']:6.2f} s")

    # ---------- 图 ----------
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2))
    labels = [r["config"] for r in rows]
    y = range(len(rows))

    ax = axes[0]
    ax.barh(y, [r["esc_p1"] for r in rows], color="#2563eb", label="1 跳")
    ax.barh(y, [r["esc_p2"] - r["esc_p1"] for r in rows], left=[r["esc_p1"] for r in rows],
            color="#93c5fd", label="2 跳")
    ax.barh(y, [1 - r["esc_p2"] for r in rows], left=[r["esc_p2"] for r in rows],
            color="#dc2626", label="≥3 跳")
    ax.set_yticks(list(y)); ax.set_yticklabels(labels, fontsize=8); ax.invert_yaxis()
    ax.set_xlabel("进影星占比"); ax.set_title("(a) 无容量限制: 到最近亮星的跳数")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)

    ax = axes[1]
    ax.barh(y, [r["cap1_mean"] or 0 for r in rows], color="#f59e0b", label="均值")
    ax.scatter([r["cap1_max"] or 0 for r in rows], list(y), color="#7c2d12", zorder=3, label="最大")
    ax.scatter([r["cap1_p90"] or 0 for r in rows], list(y), color="#dc2626", marker="|", s=200, zorder=3, label="p90")
    ax.set_yticks(list(y)); ax.set_yticklabels([]); ax.invert_yaxis()
    ax.set_xlabel("跳数"); ax.set_title("(b) 每颗亮星只接 1 颗影星 (k=1)")
    ax.legend(fontsize=8, loc="lower right")

    ax = axes[2]
    for L, c in zip(LIFE_MIN, ["#16a34a", "#2563eb", "#f59e0b", "#dc2626"]):
        ax.plot([r[f"place{L}_h1"] for r in rows], list(y), "o-", color=c, label=f"L={L} min, ≤1 跳")
    ax.set_yticks(list(y)); ax.set_yticklabels([]); ax.invert_yaxis()
    ax.set_xlim(0, 1.02); ax.set_xlabel("到达时刻占比")
    ax.set_title("(c) 星历放置: ≤1 跳内有剩余光照 ≥ L 的星")
    ax.legend(fontsize=8, loc="lower left"); ax.grid(alpha=0.3)

    fig.tight_layout()
    png = os.path.join(OUT, "shadow_escape.png")
    fig.savefig(png, dpi=150)
    print(f"\n图: {png}")


if __name__ == "__main__":
    main()
