"""Q5 修正: 日凌窗口应该跑上午星 (β 会过 0), 不是晨昏星 (|β| 全年 ≥58°)."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from orbitsim import orbit_sun as osun

alt = 650e3
inc = osun.sso_inclination_deg(alt)
print(f"650 km SSO, i={inc:.2f} deg")
print()
print(f"{'LTAN':>6} {'min|β|_deg':>11} {'|β|<1°天数':>11} {'|β|<2°天数':>11} {'|β|<5°天数':>11}")
for ltan in (6.0, 9.0, 10.5, 12.0, 13.5):
    betas = [osun.beta_angle_rad(inc, osun.solar_declination_deg(d), ltan) for d in range(366)]
    degs = [abs(math.degrees(b)) for b in betas]
    n1 = sum(1 for x in degs if x < 1.0)
    n2 = sum(1 for x in degs if x < 2.0)
    n5 = sum(1 for x in degs if x < 5.0)
    print(f"{ltan:>6} {min(degs):>11.2f} {n1:>11} {n2:>11} {n5:>11}")

print()
print("修正结论: β 的季节摆动中心由 LTAN 决定 —— 只有正午轨道 (LTAN≈12) β 才扫过 0;")
print("  上午星 (10:30) min|β|=17°, 晨昏星 (6:00) min|β|=58.6°, 两类遥感主力轨道都无日凌风险;")
print("  日凌只是 LTAN≈12 轨道 (如部分气象/海洋星) 的设计约束.")
