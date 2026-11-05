"""集群电力保障随 RAAN 粒度 + 相位因子 F 的系统扫描.

修正后的规律 (假说 v2, 已被数据验证):
1. 面数本身几乎不影响低谷深度 (2-24 面都是 ~14-15 平台) —— 假说 v1 被推翻.
2. 但 Walker 相位因子 F 有决定性作用: 每面 1 星 + F=1 时 RAAN≡u 相位锁定,
   全群同时进影, 低谷崩溃到 6/24; F≥2 时回到平台. 这是真实 Walker δ
   星座 (Starlink 等) 选 F>1 的一个被忽视的能源理由.
3. 1 面 × 24 星 (面内相位冗余, 大数定律) 与多面平台相当 (15 vs 14-16).

扫描: 24 星分为 P 面 × (24/P) 星/面, P ∈ {1,2,3,4,6,8,12,24}, F ∈ {1,2,5}.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from orbitsim import fleet_energy as fe
from orbitsim import orbit_sun as osun
from orbitsim.constellation import load_constellation, expand_satellites

OUT = os.path.join(os.path.dirname(__file__), "research_out")
ALT = 550e3
INC = osun.sso_inclination_deg(ALT)

print(f"{'planes':>7} {'sats/plane':>11} {'F':>3} {'最深低谷':>9} {'doy':>5} {'日均低谷':>9} {'日均光照':>9}")
rows = []
for F in (1, 2, 5):
    for planes in (1, 2, 3, 4, 6, 8, 12, 24):
        spp = 24 // planes
        const = load_constellation({"kind": "walker", "planes": planes,
                                    "sats_per_plane": spp, "altitude_m": ALT,
                                    "inclination_deg": INC, "phase_factor": F})
        sats = expand_satellites(const)
        days = fe.annual_summary(sats, n_days=365, n_slots=48)
        worst = min(days, key=lambda d: d["lit_min"])
        mean_min = sum(d["lit_min"] for d in days) / len(days)
        mean_mean = sum(d["lit_mean"] for d in days) / len(days)
        rows.append((planes, spp, F, worst["lit_min"], worst["doy"], mean_min, mean_mean))
        print(f"{planes:>7} {spp:>11} {F:>3} {worst['lit_min']:>9} {worst['doy']:>5} {mean_min:>9.2f} {mean_mean:>9.2f}")

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 2, figsize=(13.5, 5))

# (a) 最深低谷 vs 面数, 按 F 分组
ax = axes[0]
colors = {1: "#dc2626", 2: "#2563eb", 5: "#16a34a"}
for F in (1, 2, 5):
    sub = [r for r in rows if r[2] == F]
    ax.plot([r[0] for r in sub], [r[3] for r in sub], "o-", color=colors[F], label=f"F={F}")
ax.annotate("F=1, 24面×1星:\nRAAN≡u 相位锁定\n全群同步进影", (24, 6), xytext=(10, 8.5),
            fontsize=8, color="#dc2626",
            arrowprops=dict(arrowstyle="->", color="#dc2626"))
ax.set_xscale("log", base=2)
xs = sorted({r[0] for r in rows})
ax.set_xticks(xs); ax.set_xticklabels([str(x) for x in xs])
ax.set_xlabel("轨道面数 (总星数固定 24)")
ax.set_ylabel("最深低谷 (全年最坏时刻光照星数)")
ax.set_title("(a)  低谷深度 vs 面数 × 相位因子 F")
ax.legend(); ax.grid(alpha=0.3, which="both")
ax.set_ylim(4, 18)

# (b) 日均光照 (r[6], 总量) vs 日均低谷 (r[5], 分布) —— 总量相同, 分布天差地别
ax = axes[1]
for F in (1, 2, 5):
    sub = [r for r in rows if r[2] == F]
    ax.plot([r[0] for r in sub], [r[6] for r in sub], "s-", color=colors[F],
            label=f"F={F} 日均光照(总量)")
ax.plot([r[0] for r in rows if r[2] == 1], [r[5] for r in rows if r[2] == 1],
        "v--", color="#dc2626", label="F=1 日均低谷(分布)")
ax.annotate("F=1, 24面: 总能量与别人相同\n但集中在少数时段交付", (24, 7.14),
            xytext=(5.5, 9.5), fontsize=8, color="#dc2626",
            arrowprops=dict(arrowstyle="->", color="#dc2626"))
ax.set_xscale("log", base=2)
ax.set_xticks(xs); ax.set_xticklabels([str(x) for x in xs])
ax.set_xlabel("轨道面数 (总星数固定 24)")
ax.set_ylabel("光照星数")
ax.set_title("(b)  总量处处相同 (~17.7), 低谷分布由 F/结构决定")
ax.legend(fontsize=8); ax.grid(alpha=0.3, which="both")

fig.tight_layout()
png = os.path.join(OUT, "raan_granularity.png")
fig.savefig(png, dpi=150)
print(f"\n图已存: {png}")
