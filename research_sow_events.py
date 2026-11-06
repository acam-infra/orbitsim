"""SOW 合作点二的几何前提核查: 用星历把"可预测中断"算出来.

依据: LAB-1726 + 飞书《在轨长程推理连续性保障: 核心机制设计与技术方案专研》.
专研文档的系统模型:
  - 算力星分 K 个"编队紧凑"的簇, 簇内固定激光 25 Gbps, 跨簇 2-3 条动态骨干 10 Gbps;
  - f_i(t) = f_nom · α_orbit(t) · α_payload(t) · I_alive(t), α_orbit 由星历先验已知;
  - 轨 A: 关断前提前 Δt 迁移关键请求到"错相空闲"的邻星;
  - 1.2 节: "高算力窗口通常仅能维持数十秒至数百秒";
  - LAB-1687 sim.py: 每簇地影 2100 s / 轨道 5700 s, 各簇相位按 c/C 均匀错开.

要核的前提:
  P1 簇内是不是同时进影?  (决定轨 A 能否在 25 Gbps 簇内逃逸, 还是必须走 10 Gbps 跨簇)
  P2 各簇地影时长是否都 ≈ 2100 s, 相位是否均匀错开?  (sim.py 的假设)
  P3 地影窗口有多长? 一个长任务 (寿命 L) 跨越关断的概率多大?  (决定轨 A 能救多少)
  P4 关断时刻, 最近的亮簇在哪, 跨簇链路此刻是否可见 (≤ R_ISL, 视线不擦地球)?
  P5 提前量 Δt: 星历给的是确定时刻, 能提前多少? (不是问题, 但要给数)
  P6 "周期性关闭 + 5% 失效" 下, 无保障机制损失多少长任务产出 → SOW +20% 是否几何上可达.

构型 (16 星 = 4 簇 × 4 星, 550 km):
  S-SSO4   4 个 SSO 面, LTAN 0/6/12/18 h (RAAN 均布), 每面 1 簇
  S-SSO2   2 个 SSO 面 (LTAN 10.5 / 13.5, 贴遥感星), 每面 2 簇 (相隔 180°)
  S-W53    4 个 53° 面 RAAN 均布, 每面 1 簇
  簇内间隔 Δu = 2° (≈ 240 km).
"""
from __future__ import annotations

import csv
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from orbitsim import fleet_synth as fs

OUT = os.path.join(os.path.dirname(__file__), "research_out")
os.makedirs(OUT, exist_ok=True)

DT = 5.0
T = np.arange(0.0, 86400.0, DT)
SEASONS = {"春分": 81.0, "夏至": 172.0, "冬至": 355.0}
ALT = 550.0
DU = 2.0
R_ISL = 5000e3
LIFE_MIN = [3, 6, 9, 20]     # 长任务寿命 (LAB-1687: 6k-18k tok × ~30 ms ≈ 3-9 min; agentic 多轮可到 20 min)
STATIONS = {"密云": (40.4, 116.9), "喀什": (39.5, 76.0), "三亚": (18.3, 109.3)}


def cluster(prefix, n, *, ltan=None, inc=None, raan=None, u0=0.0):
    out = []
    for k in range(n):
        kw = dict(ltan_h=ltan) if ltan is not None else dict(inc_deg=inc, raan_deg=raan)
        out.append(fs.make_sat(f"{prefix}/s{k}", ALT, u0_deg=u0 + DU * k, role="compute", **kw))
    return out


def build():
    cfgs = {}
    cfgs["S-SSO4 (LTAN 0/6/12/18)"] = [cluster(f"c{c}", 4, ltan=(6.0 * c) % 24, u0=90.0 * c) for c in range(4)]
    cfgs["S-SSO2 (LTAN 10.5/13.5 ×2簇)"] = [
        cluster("c0", 4, ltan=10.5, u0=0.0), cluster("c1", 4, ltan=10.5, u0=180.0),
        cluster("c2", 4, ltan=13.5, u0=90.0), cluster("c3", 4, ltan=13.5, u0=270.0)]
    cfgs["S-W53 (53° RAAN 均布)"] = [cluster(f"c{c}", 4, inc=53.0, raan=90.0 * c, u0=90.0 * c) for c in range(4)]
    return cfgs


def edges(mask):
    """(start_idx, end_idx) of True runs."""
    m = np.r_[False, mask, False].astype(int)
    d = np.diff(m)
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def analyse(clusters, doy):
    sats = [s for c in clusters for s in c]
    cid = np.array([ci for ci, c in enumerate(clusters) for _ in c])
    pos = fs.positions(sats, doy, T)
    lit = fs.lit(pos, fs.sun_vec(doy))           # (T, N)
    dark = ~lit
    N = len(sats)

    # P1: 簇内进影时刻差
    intra_skew = []
    for ci, c in enumerate(clusters):
        idx = np.where(cid == ci)[0]
        starts = [[a for a, _ in edges(dark[:, i])] for i in idx]
        if not starts[0]:
            continue
        for a0 in starts[0]:
            if a0 == 0 or a0 > len(T) - 1800 / DT:   # 跳过日界被截断的地影段
                continue
            others = []
            for s in starts[1:]:
                if s:
                    others.append(min(abs(a - a0) for a in s))
            if others:
                intra_skew.append(max(others) * DT)

    # P2: 每簇地影时长 / 每轨地影比例, 以及簇间进影相位
    per_cluster = []
    for ci, c in enumerate(clusters):
        i = np.where(cid == ci)[0][0]
        runs = [(b - a) * DT for a, b in edges(dark[:, i]) if a > 0 and b < len(T)]
        per_cluster.append({"dark_frac": float(dark[:, i].mean()),
                            "dark_run_min": (np.mean(runs) / 60) if runs else 0.0,
                            "lit_run_min": (np.mean([(b - a) * DT for a, b in edges(lit[:, i])
                                                     if a > 0 and b < len(T)]) / 60) if runs else float("inf")})

    # P3: 寿命 L 的请求, 均匀到达在亮星上, 寿命内撞上关断的概率
    cross = {}
    for L in LIFE_MIN:
        k = int(L * 60 / DT)
        hit, tot = 0, 0
        for i in range(N):
            d = dark[:, i]
            # 未来 k 步内出现 dark 的前缀判断: 用滑窗 OR
            cs = np.r_[0, np.cumsum(d)]
            fut = cs[np.minimum(np.arange(len(T)) + k, len(T))] - cs[np.arange(len(T))]
            ok = lit[:, i]
            hit += int(np.sum((fut > 0) & ok))
            tot += int(np.sum(ok))
        cross[L] = hit / tot

    # P4: 每次进影时刻, 同簇是否全暗; 最近亮簇的跨簇链路是否可见
    rng, clear = fs.los_range(pos, pos)
    reach = clear & (rng <= R_ISL)
    n_entry, intra_lit_avail, cross_lit_avail, cross_any = 0, 0, 0, 0
    for i in range(N):
        for a, _ in edges(dark[:, i]):
            if a == 0:
                continue
            n_entry += 1
            same = (cid == cid[i]) & (np.arange(N) != i)
            other = cid != cid[i]
            if np.any(same & lit[a]):
                intra_lit_avail += 1
            if np.any(other & lit[a]):
                cross_any += 1
            if np.any(other & lit[a] & reach[a, i]):
                cross_lit_avail += 1

    # P6: 无保障: 撞上关断的请求作废; 损失长任务产出比例 ≈ cross[L]; 加 5% 失效
    return {
        "intra_skew_max_s": max(intra_skew) if intra_skew else 0.0,
        "per_cluster": per_cluster,
        "cross": cross,
        "n_entry": n_entry,
        "entry_intra_lit": intra_lit_avail / n_entry if n_entry else float("nan"),
        "entry_cross_lit_any": cross_any / n_entry if n_entry else float("nan"),
        "entry_cross_lit_reach": cross_lit_avail / n_entry if n_entry else float("nan"),
        "fleet_dark_frac": float(dark.mean()),
        "all_dark_frac": float(dark.all(axis=1).mean()),
    }


def main():
    cfgs = build()
    rows = []
    for name, clusters in cfgs.items():
        for season, doy in SEASONS.items():
            r = analyse(clusters, doy)
            pc = r.pop("per_cluster")
            cr = r.pop("cross")
            row = {"config": name, "season": season, **r}
            for ci, p in enumerate(pc):
                row[f"c{ci}_dark_frac"] = p["dark_frac"]
                row[f"c{ci}_dark_min"] = p["dark_run_min"]
                row[f"c{ci}_lit_min"] = p["lit_run_min"]
            for L, v in cr.items():
                row[f"cross_L{L}"] = v
            rows.append(row)
            print(f"done {name} {season}", flush=True)

    with open(os.path.join(OUT, "sow_events.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})

    print("\nP1/P2 簇内同步 & 各簇地影")
    for r in rows:
        cl = " | ".join(f"c{c}: 影{r[f'c{c}_dark_frac']:.0%} 段{r[f'c{c}_dark_min']:.0f}m 亮段{r[f'c{c}_lit_min']:.0f}m"
                        for c in range(4))
        print(f"{r['config']:>28} {r['season']} 簇内进影最大时差 {r['intra_skew_max_s']:5.0f}s  {cl}  全暗时刻 {r['all_dark_frac']:.0%}")
    print("\nP3 长任务寿命内撞上地影的概率 / P4 进影时刻的逃逸对象")
    for r in rows:
        cr = " ".join(f"L={L}m:{r[f'cross_L{L}']:.1%}" for L in LIFE_MIN)
        print(f"{r['config']:>28} {r['season']} {cr}  | 进影时 簇内有亮星 {r['entry_intra_lit']:.0%}  "
              f"别簇有亮星 {r['entry_cross_lit_any']:.0%}  且链路可见 {r['entry_cross_lit_reach']:.0%}")

    # ---------- 图: 每个构型春分 24h 的 16 星光照甘特图 ----------
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(cfgs), 1, figsize=(15, 3.2 * len(cfgs)), sharex=True)
    for ax, (name, clusters) in zip(axes, cfgs.items()):
        sats = [s for c in clusters for s in c]
        tt = T[T < 6 * 3600]
        pos = fs.positions(sats, 81.0, tt)
        dk = ~fs.lit(pos, fs.sun_vec(81.0))
        ax.imshow(dk.T, aspect="auto", cmap="Greys", interpolation="nearest",
                  extent=[0, tt[-1] / 60, len(sats) - 0.5, -0.5])
        for c in range(1, 4):
            ax.axhline(4 * c - 0.5, color="#dc2626", lw=1)
        ax.set_yticks([1.5, 5.5, 9.5, 13.5]); ax.set_yticklabels(["簇0", "簇1", "簇2", "簇3"])
        ax.set_title(f"{name}: 春分前 6 h, 黑 = 地影 (红线分簇)")
    axes[-1].set_xlabel("min")
    fig.tight_layout()
    png = os.path.join(OUT, "sow_events.png")
    fig.savefig(png, dpi=130)
    print(f"\n图: {png}")


if __name__ == "__main__":
    main()
