"""互证: 用 orbitsim 独立复算 gjam LAB-714 / ANALYSIS.md 里的关键数字.

两套独立代码 (orbitsim 的 J2+圆柱地影 vs leo-datacenter-cluster 的
太阳锥模型+SGP4) 推出同一批数, 是论文里最值钱的可信度证据.

对照点 (LAB-714 已记录数值):
  1. 晨昏 650 km 冬至日影 ≈ 19.7 min/圈
  2. 晨昏全日照隐含高度 ≈ 1500 km
  3. 650 km 无影门限 |β| ≥ 65.16°
  4. LTAN 10:30 全年日影 ≈ 34 min/圈 (春秋分/夏至/冬至 34.2/34.0/34.7)
  5. ANALYSIS.md 的太阳锥模型 β=82° 全年 0 影 —— 与真实 β 摆幅的差距
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from orbitsim import orbit_sun as osun

print("orbitsim 独立复算 vs gjam LAB-714/ANALYSIS.md 已记录值")
print("=" * 72)

# 1. 晨昏 650 km 全年逐日日影, 冬至 (doy 355) 附近峰值
alt = 650e3
inc = osun.sso_inclination_deg(alt)
peak = 0.0
for doy in range(365):
    beta = osun.beta_angle_rad(inc, osun.solar_declination_deg(doy), 6.0)
    peak = max(peak, osun.eclipse_minutes(alt, beta))
print(f"1. 晨昏 650 km 冬至日影峰值: orbitsim={peak:.1f} min/圈   LAB-714=19.7 min/圈")

# 2. 晨昏全日照隐含高度
clear = osun.dawn_dusk_clear_altitude_m()
print(f"2. 晨昏全日照隐含高度:      orbitsim={clear/1e3:.0f} km      LAB-714=~1500 km")

# 3. 650 km 无影门限
thr = osun.eclipse_threshold_deg(alt)
print(f"3. 650 km 无影门限 |β|:      orbitsim={thr:.2f} deg    LAB-714=65.16 deg")

# 4. LTAN 10:30 三季日影
for name, doy in (("春秋分", 81), ("夏至", 172), ("冬至", 355)):
    beta = osun.beta_angle_rad(inc, osun.solar_declination_deg(doy), 10.5)
    e = osun.eclipse_minutes(alt, beta)
    print(f"4. LTAN 10:30 {name}:       orbitsim={e:.1f} min/圈   LAB-714≈34 min/圈")

# 5. ANALYSIS.md 太阳锥 β=82° 与真实晨昏 β 摆幅的差距
b_min = min(
    abs(osun.beta_angle_rad(inc, +osun.OBLIQUITY_DEG, 6.0)),
    abs(osun.beta_angle_rad(inc, -osun.OBLIQUITY_DEG, 6.0)),
)
import math
print(f"5. 真实晨昏 650 km 年内 min|β|={math.degrees(b_min):.1f} deg  "
      f"(ANALYSIS.md 太阳锥钉在 82 deg, 全年 0 影)")
print(f"   => 太阳锥模型把季节性 β 摆幅 (~{82-math.degrees(b_min):.0f} deg) 简化没了,")
print(f"      冬至前后的 {peak:.0f} min/圈 日影被它完全漏掉.")
