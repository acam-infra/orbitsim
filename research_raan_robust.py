"""稳健性检查: 24面×1星 的深谷 (6/24) 是物理真实还是相位锁定假象?

F=1 时第 p 颗星 (RAAN=15p, u=15p): RAAN≡u, 存在隐含相位对齐.
扫 phase_factor F ∈ {1,2,5,7} + 整体相位偏移, 看低谷深度是否稳定.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from orbitsim import fleet_energy as fe
from orbitsim import orbit_sun as osun
from orbitsim.constellation import load_constellation, expand_satellites

ALT = 550e3
INC = osun.sso_inclination_deg(ALT)

print(f"{'F':>3} {'phase_off':>10} {'最深低谷':>9} {'doy':>5} {'日均低谷':>9} {'日均光照':>9}")
for F in (1, 2, 5, 7):
    for off in (0.0, 7.5):
        const = load_constellation({"kind": "walker", "planes": 24, "sats_per_plane": 1,
                                    "altitude_m": ALT, "inclination_deg": INC,
                                    "phase_factor": F, "phase_offset_deg": off})
        sats = expand_satellites(const)
        days = fe.annual_summary(sats, n_days=365, n_slots=96)
        worst = min(days, key=lambda d: d["lit_min"])
        mean_min = sum(d["lit_min"] for d in days) / len(days)
        mean_mean = sum(d["lit_mean"] for d in days) / len(days)
        print(f"{F:>3} {off:>10} {worst['lit_min']:>9} {worst['doy']:>5} {mean_min:>9.2f} {mean_mean:>9.2f}")

# 对照: 同面 1×24 在不同 F 下应当完全不变 (面内相位均匀铺满, F 无意义)
print()
print("对照 1面×24星 (应与 F 无关):")
for F in (1, 3):
    const = load_constellation({"kind": "walker", "planes": 1, "sats_per_plane": 24,
                                "altitude_m": ALT, "inclination_deg": INC,
                                "phase_factor": F})
    sats = expand_satellites(const)
    days = fe.annual_summary(sats, n_days=365, n_slots=96)
    worst = min(days, key=lambda d: d["lit_min"])
    mean_mean = sum(d["lit_mean"] for d in days) / len(days)
    print(f"  F={F}: 最深低谷={worst['lit_min']} (doy {worst['doy']}), 日均光照={mean_mean:.2f}")
