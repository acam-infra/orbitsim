"""集群能源: 异构卫星群随时间的光照演化.

科学问题: 从整个星座看, 任意时刻保证有多少星在光照 (可开机/可中继)?

对比 4 种 24 星配置 (同样的星数, 不同的"异构程度"):
  A 单壳 4面×6星  @550 km           —— 基线
  B 单壳 8面×3星  @550 km           —— 面数加倍, RAAN 更密
  C 双壳 2×6@550 + 2×6@800 km       —— 高度异构 (周期不同, 相位随时间漂移)
  D 双壳 2×6@550 + 2×6@550(phase+30°) —— 同高度相位异构 (兄弟壳)

指标:
  - 全年逐日 min/mean 光照星数 (电力低谷深度 + 季节摆动)
  - 全年最深低谷 (worst instant) 与发生日期
  - 一天内光照星数波动 (低谷时长)
  - 至点日 24h 逐槽曲线 (低谷长什么样)
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from orbitsim import fleet_energy as fe
from orbitsim import orbit_sun as osun
from orbitsim.constellation import load_constellation, expand_satellites

OUT = os.path.join(os.path.dirname(__file__), "research_out")
os.makedirs(OUT, exist_ok=True)

N_DAYS = 365
N_SLOTS = 96  # 每天 96 槽 (15 min 分辨率)


def cfg_A():
    return {"kind": "walker", "planes": 4, "sats_per_plane": 6,
            "altitude_m": 550e3, "inclination_deg": osun.sso_inclination_deg(550e3)}


def cfg_B():
    return {"kind": "walker", "planes": 8, "sats_per_plane": 3,
            "altitude_m": 550e3, "inclination_deg": osun.sso_inclination_deg(550e3)}


def cfg_C():
    # 两壳各 2面×6星 = 12 星, 共 24 星, 高度异构
    return {"shells": [
        {"name": "lo", "kind": "walker", "planes": 2, "sats_per_plane": 6,
         "altitude_m": 550e3, "inclination_deg": osun.sso_inclination_deg(550e3)},
        {"name": "hi", "kind": "walker", "planes": 2, "sats_per_plane": 6,
         "altitude_m": 800e3, "inclination_deg": osun.sso_inclination_deg(800e3)},
    ]}


def cfg_D():
    # 两壳各 2面×6星 = 12 星, 共 24 星, 同高度相位异构
    return {"shells": [
        {"name": "a", "kind": "walker", "planes": 2, "sats_per_plane": 6,
         "altitude_m": 550e3, "inclination_deg": osun.sso_inclination_deg(550e3)},
        {"name": "b", "kind": "walker", "planes": 2, "sats_per_plane": 6,
         "altitude_m": 550e3, "inclination_deg": osun.sso_inclination_deg(550e3),
         "phase_offset_deg": 30.0},
    ]}


CONFIGS = {
    "A 单壳4×6@550": cfg_A(),
    "B 单壳8×3@550": cfg_B(),
    "C 高度异构550+800": cfg_C(),
    "D 相位异构550+550": cfg_D(),
}


def main():
    results = {}
    for label, cfg in CONFIGS.items():
        const = load_constellation(cfg)
        sats = expand_satellites(const)
        assert len(sats) == 24, f"{label}: {len(sats)} sats, want 24"
        print(f"扫 {label} ({len(sats)} 星 × {N_DAYS} 天 × {N_SLOTS} 槽) ...", flush=True)
        days = fe.annual_summary(sats, N_DAYS, N_SLOTS)
        worst = min(days, key=lambda d: d["lit_min"])
        mean_of_min = sum(d["lit_min"] for d in days) / len(days)
        mean_of_mean = sum(d["lit_mean"] for d in days) / len(days)
        # 低谷日 24h 曲线
        valley_profile = fe.daily_profile(sats, worst["doy"], N_SLOTS)
        results[label] = {
            "days": days, "worst": worst, "valley_profile": valley_profile,
            "mean_of_min": mean_of_min, "mean_of_mean": mean_of_mean,
        }

    # ---------- 终端汇总 ----------
    print()
    print("=" * 84)
    print("集群级电力可用性对比 (24 星, 全年)")
    print("=" * 84)
    print(f"{'配置':>22} {'最深低谷(星)':>13} {'发生日doy':>10} {'日均低谷':>9} {'日均光照':>9} {'低谷占比':>9}")
    for label, r in results.items():
        w = r["worst"]
        valley_frac = w["lit_min"] / 24
        print(f"{label:>22} {w['lit_min']:>13} {w['doy']:>10} "
              f"{r['mean_of_min']:>9.2f} {r['mean_of_mean']:>9.2f} {valley_frac:>8.0%}")

    # ---------- CSV ----------
    for label, r in results.items():
        fn = os.path.join(OUT, f"fleet_{label.split()[0]}.csv")
        with open(fn, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["doy", "lit_min", "lit_mean", "lit_max"])
            for d in r["days"]:
                w.writerow([d["doy"], d["lit_min"], round(d["lit_mean"], 2), d["lit_max"]])

    # ---------- 图 ----------
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt

    colors = {"A 单壳4×6@550": "#2563eb", "B 单壳8×3@550": "#0ea5e9",
              "C 高度异构550+800": "#dc2626", "D 相位异构550+550": "#f59e0b"}

    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9))

    # (a) 全年逐日电力低谷 (lit_min)
    ax = axes[0, 0]
    for label, r in results.items():
        ax.plot([d["doy"] for d in r["days"]], [d["lit_min"] for d in r["days"]],
                label=label, color=colors[label], lw=1.2)
    ax.set_xlabel("day of year"); ax.set_ylabel("min lit sats (daily worst instant)")
    ax.set_title("(a)  电力低谷: 每天最深时刻的光照星数")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # (b) 全年逐日平均光照
    ax = axes[0, 1]
    for label, r in results.items():
        ax.plot([d["doy"] for d in r["days"]], [d["lit_mean"] for d in r["days"]],
                label=label, color=colors[label], lw=1.2)
    ax.set_xlabel("day of year"); ax.set_ylabel("mean lit sats")
    ax.set_title("(b)  日平均光照星数 (季节摆动)")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # (c) 至点日 24h 逐槽曲线 (低谷长什么样)
    ax = axes[1, 0]
    for label, r in results.items():
        ax.plot([k * 24 / N_SLOTS for k in range(N_SLOTS)], r["valley_profile"],
                label=f"{label} (doy {r['worst']['doy']})", color=colors[label], lw=1.4)
    ax.set_xlabel("hour of day"); ax.set_ylabel("lit sats")
    ax.set_title("(c)  各自最深低谷日的 24h 光照曲线")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # (d) 低谷深度直方对比 + 关键数字标注
    ax = axes[1, 1]
    labels = list(results.keys())
    worsts = [results[l]["worst"]["lit_min"] for l in labels]
    bars = ax.bar(range(len(labels)), worsts, color=[colors[l] for l in labels], alpha=0.85)
    ax.axhline(24, color="#64748b", ls="--", lw=1)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([l.replace(" ", "\n") for l in labels], fontsize=8)
    ax.set_ylabel("annual worst instant (lit sats of 24)")
    ax.set_title("(d)  全年最深电力低谷对比")
    for b, v in zip(bars, worsts):
        ax.annotate(str(v), (b.get_x() + b.get_width() / 2, v), ha="center", va="bottom", fontsize=10)
    ax.set_ylim(0, 25); ax.grid(alpha=0.3, axis="y")

    fig.tight_layout()
    png = os.path.join(OUT, "fleet_energy.png")
    fig.savefig(png, dpi=150)
    print(f"\n图已存: {png}")
    print(f"CSV 目录: {OUT}")


if __name__ == "__main__":
    main()
