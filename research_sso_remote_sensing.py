"""科研分析: SSO 合成 + 遥感轨道规律性数据.

用 orbitsim 的闭式解模块做参数扫描, 回答几个典型的轨道设计问题:

Q1  SSO 倾角随高度怎么变? (J2 闭式 vs 经验值)
Q2  晨昏 SSO (LTAN=6/18) 是不是全年无影? 无影高度门限多少?
Q3  上午星 (LTAN=10.5, 高分/资源风格) 一年晒不到太阳多久? 日影随季节怎么变?
Q4  同一颗遥感星对北京/喀什两个站的日均可访问时间差多少?
Q5  日凌窗口: 全年有多少天链路可能被太阳干扰?

输出: 终端表格 + research_out/ 下的 CSV + matplotlib 图 (若装了 matplotlib).
"""
from __future__ import annotations

import csv
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from orbitsim import orbit_sun as osun
from orbitsim import visibility as vis

OUT = os.path.join(os.path.dirname(__file__), "research_out")
os.makedirs(OUT, exist_ok=True)

YEAR_DAYS = 365.2422


def sec_row(title: str):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------- Q1 SSO 合成
sec_row("Q1  SSO 合成表: 高度 -> 倾角/周期/每天圈数 (J2 闭式解)")
print(f"{'alt_km':>8} {'sso_inc_deg':>12} {'period_min':>11} {'rev/day':>8} {'eclipse_thresh_|β|_deg':>22}")
q1_rows = []
for alt_km in (400, 500, 550, 600, 650, 700, 800, 900, 1000, 1200, 1400):
    alt = alt_km * 1e3
    inc = osun.sso_inclination_deg(alt)
    T_min = osun.chief_period_s(alt) / 60.0
    rev = 1440.0 / T_min
    thr = osun.eclipse_threshold_deg(alt)
    print(f"{alt_km:>8} {inc:>12.3f} {T_min:>11.2f} {rev:>8.2f} {thr:>22.2f}")
    q1_rows.append((alt_km, round(inc, 4), round(T_min, 3), round(rev, 3), round(thr, 3)))

with open(os.path.join(OUT, "q1_sso_synthesis.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["alt_km", "sso_inclination_deg", "period_min", "rev_per_day", "eclipse_free_abs_beta_deg"])
    w.writerows(q1_rows)


# --------------------------------------------- Q2 晨昏 SSO 全年无影高度门限
sec_row("Q2  晨昏 SSO (LTAN=06:00) 全年无影高度门限")
clear_alt = osun.dawn_dusk_clear_altitude_m()
print(f"全年无影最低高度 ≈ {clear_alt/1e3:.1f} km")
print("(低于此高度, 晨昏轨道在夏至/冬至前后仍会短暂进地影)")
print()
print(f"{'alt_km':>8} {'sso_inc':>8} {'min|β|_year_deg':>16} {'eclipse_thr':>12} {'全年无影?':>10}")
for alt_km in (400, 500, 550, 560, 570, 600, 650, 700, 800):
    alt = alt_km * 1e3
    inc = osun.sso_inclination_deg(alt)
    min_beta = math.degrees(osun.dawn_dusk_min_abs_beta_rad(alt))
    thr = osun.eclipse_threshold_deg(alt)
    clear = "是" if min_beta >= thr else "否"
    print(f"{alt_km:>8} {inc:>8.2f} {min_beta:>16.2f} {thr:>12.2f} {clear:>10}")


# --------------------------- Q3 上午星 vs 晨昏星: 全年日影曲线 (遥感设计核心)
sec_row("Q3  650 km SSO 全年逐日日影: 晨昏(LTAN=6) vs 上午(LTAN=10.5) vs 正午(LTAN=12)")
alt = 650e3
inc = osun.sso_inclination_deg(alt)
T_min = osun.chief_period_s(alt) / 60.0
print(f"alt=650 km, SSO inc={inc:.2f} deg, period={T_min:.1f} min")
print(f"{'doy':>5} {'decl_deg':>9} {'β_LTAN6':>9} {'ecl6_min':>9} {'β_LTAN10.5':>11} {'ecl10.5_min':>12} {'β_LTAN12':>9} {'ecl12_min':>10}")

q3_rows = []
annual_eclipse_h = {6.0: 0.0, 10.5: 0.0, 12.0: 0.0}
for doy in range(0, 366, 7):
    decl = osun.solar_declination_deg(doy)
    row = [doy, round(decl, 2)]
    for ltan in (6.0, 10.5, 12.0):
        beta = osun.beta_angle_rad(inc, decl, ltan)
        ecl_min = osun.eclipse_minutes(alt, beta)
        row += [round(math.degrees(beta), 2), round(ecl_min, 2)]
        # 全年累计日影小时: 每圈日影分钟 × 每天圈数 × 7 天
        annual_eclipse_h[ltan] += ecl_min * (1440.0 / T_min) * 7 / 60.0
    q3_rows.append(row)
    if doy % 28 == 0:
        print(f"{row[0]:>5} {row[1]:>9} {row[2]:>9} {row[3]:>9} {row[4]:>11} {row[5]:>12} {row[6]:>9} {row[7]:>10}")

print()
print("全年累计日影小时数 (越低越利于能源/热控):")
for ltan, h in annual_eclipse_h.items():
    print(f"  LTAN={ltan:>4}: {h:7.1f} h/年  (占全年 {h/ (365.2422*24) *100:.2f}%)")

with open(os.path.join(OUT, "q3_eclipse_year_650km.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["doy", "decl_deg", "beta_ltan6_deg", "eclipse_min_ltan6",
                "beta_ltan10p5_deg", "eclipse_min_ltan10p5",
                "beta_ltan12_deg", "eclipse_min_ltan12"])
    w.writerows(q3_rows)


# --------------------------- Q4 地面站可见: 北京 vs 喀什, 高度扫描
sec_row("Q4  遥感星地面站日均可访问分钟 (order-of-magnitude 闭式)")
print("⚠ 模型边界: visibility.py 的 access_fraction_equatorial 不含纬度参数,")
print("  对近极轨 SSO (i≈98°) 三站算出同一值 —— 说明该近似只能做高度权衡,")
print("  不能用于站址对比. 逐站差异需要真星下点轨迹 (sgp4/astropy) 才能给出.")
sites = {"北京(39.9N)": 39.9, "喀什(39.5N)": 39.5, "三亚(18.3N)": 18.3}
print(f"{'alt_km':>8} {'inc_sso':>8}", end="")
for name in sites:
    print(f" {name:>14}", end="")
print()
q4_rows = []
for alt_km in (500, 600, 650, 700, 800):
    alt = alt_km * 1e3
    inc = osun.sso_inclination_deg(alt)
    row = [alt_km, round(inc, 2)]
    print(f"{alt_km:>8} {inc:>8.2f}", end="")
    for name, lat in sites.items():
        try:
            mins = vis.daily_access_minutes(alt, inc, lat) if hasattr(vis, "daily_access_minutes") else None
        except Exception:
            mins = None
        if mins is None:
            # 用已有 API 拼: access_fraction_equatorial × 纬度因子 × 每天轨道周期
            frac = vis.access_fraction_equatorial(alt, 10.0)
            T_min = osun.chief_period_s(alt) / 60.0
            lat_factor = math.cos(math.radians(lat)) / math.cos(math.radians(min(lat, inc if inc < 90 else 180 - inc)))
            mins = frac * T_min * (1440.0 / T_min) * max(lat_factor, 0.0)
        row.append(round(mins, 1))
        print(f" {mins:>14.1f}", end="")
    print()
    q4_rows.append(row)

with open(os.path.join(OUT, "q4_ground_access.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["alt_km", "sso_inc_deg"] + [f"daily_min_{n}" for n in sites])
    w.writerows(q4_rows)


# --------------------------- Q5 日凌窗口
sec_row("Q5  日凌 (sun-transit) 窗口: 全年 |β| 小于门限的天数比例")
print("(晨昏轨道太阳总在轨道面附近, 日凌风险看 |β| 小的日子)")
alt = 650e3
inc = osun.sso_inclination_deg(alt)
for thresh in (1.0, 2.0, 5.0):
    days = sum(
        1 for doy in range(366)
        if abs(math.degrees(osun.beta_angle_rad(inc, osun.solar_declination_deg(doy), 6.0))) < thresh
    )
    print(f"  |β| < {thresh:>3.1f} deg: {days:>3} 天/年 ({days/365.2422*100:.1f}%)")


# --------------------------- 画图
try:
    import matplotlib
    matplotlib.use("Agg")
    # Windows 中文字体, 避免 CJK 图例变方框
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9))

    # (a) SSO 倾角-高度曲线
    alts = [r[0] for r in q1_rows]
    incs = [r[1] for r in q1_rows]
    ax = axes[0, 0]
    ax.plot(alts, incs, "o-", color="#2563eb")
    ax.set_xlabel("altitude (km)")
    ax.set_ylabel("SSO inclination (deg)")
    ax.set_title("(a)  SSO inclination vs altitude (J2 closed form)")
    ax.grid(alpha=0.3)
    for a, i in zip(alts, incs):
        ax.annotate(f"{i:.1f}", (a, i), textcoords="offset points", xytext=(0, 7), fontsize=7.5, ha="center")

    # (b) 晨昏 SSO 全年 min|β| vs 无影门限, 找 1391 km 交叉
    ax = axes[0, 1]
    hs = list(range(300, 1501, 25))
    min_betas = [math.degrees(osun.dawn_dusk_min_abs_beta_rad(h * 1e3)) for h in hs]
    thrs = [osun.eclipse_threshold_deg(h * 1e3) for h in hs]
    ax.plot(hs, min_betas, label="annual min |β| (dawn-dusk)", color="#16a34a")
    ax.plot(hs, thrs, label="eclipse-free threshold asin(RE/r)", color="#dc2626", ls="--")
    ax.axvline(clear_alt / 1e3, color="#64748b", lw=1, ls=":")
    ax.annotate(f"clear ≈ {clear_alt/1e3:.0f} km", (clear_alt / 1e3, 62), rotation=90, fontsize=8, va="center")
    ax.set_xlabel("altitude (km)")
    ax.set_ylabel("angle (deg)")
    ax.set_title("(b)  Dawn-dusk SSO: min |β| vs eclipse threshold")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # (c) 650 km 三种 LTAN 全年逐圈日影
    ax = axes[1, 0]
    doys = [r[0] for r in q3_rows]
    ax.plot(doys, [r[3] for r in q3_rows], label="LTAN 06:00 (晨昏)", color="#16a34a", lw=2)
    ax.plot(doys, [r[5] for r in q3_rows], label="LTAN 10:30 (上午星)", color="#dc2626")
    ax.plot(doys, [r[7] for r in q3_rows], label="LTAN 12:00 (正午)", color="#9333ea")
    ax.set_xlabel("day of year")
    ax.set_ylabel("umbra minutes per orbit")
    ax.set_title("(c)  650 km SSO per-orbit eclipse vs season")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # (d) β 角全年演化, 五种 LTAN —— 解释日凌窗口
    ax = axes[1, 1]
    for ltan, c in ((6.0, "#16a34a"), (9.0, "#0ea5e9"), (10.5, "#dc2626"), (12.0, "#9333ea"), (13.5, "#f59e0b")):
        series = [math.degrees(osun.beta_angle_rad(inc, osun.solar_declination_deg(d), ltan)) for d in range(0, 366, 3)]
        ax.plot(range(0, 366, 3), series, label=f"LTAN {ltan:g}", color=c)
    ax.axhline(0, color="#64748b", lw=0.8)
    ax.set_xlabel("day of year")
    ax.set_ylabel("β angle (deg)")
    ax.set_title("(d)  β angle over the year — sun-transit only when β≈0 (LTAN 12)")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)

    fig.tight_layout()
    png = os.path.join(OUT, "sso_research.png")
    fig.savefig(png, dpi=150)
    print(f"\n图已存: {png}")
except ImportError:
    print("\n(没装 matplotlib, 只出 CSV)")

print(f"\nCSV 输出目录: {OUT}")
