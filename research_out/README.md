# research_out — SSO / 遥感轨道规律分析

由 `research_sso_remote_sensing.py` + `research_q5_suntransit.py` 生成, 数据全来自
orbitsim 的闭式解 (圆轨道 / 球形地球 / 圆柱形地影 / J2 长期 RAAN 漂移).

## 文件

| 文件 | 内容 |
|---|---|
| `sso_research.png` | 2×2 图: SSO 倾角-高度 / 晨昏无影门限 / 逐圈日影季节曲线 / β 角全年演化 |
| `q1_sso_synthesis.csv` | 400–1400 km SSO 合成表 (倾角, 周期, 每天圈数, 无影 β 门限) |
| `q3_eclipse_year_650km.csv` | 650 km 三种 LTAN 逐日 β 与日影分钟 |

## 核心规律

1. **SSO 倾角-高度**: 650 km→97.99°, 1400 km→101.43°, 与 J2 经验值吻合.
2. **晨昏"全年无影"要 1391 km 才成立** —— 650 km 晨昏星冬至前后仍有 ~19 min/圈日影.
3. **能源权衡**: 晨昏星年日影 371 h (4.2%), 上午星 3125 h (35.7%), 差 8.4 倍.
4. **日凌只约束 LTAN≈12 轨道** —— 10:30 上午星 min|β|=17°, 6:00 晨昏星 min|β|=58.6°, 都无风险.
5. **模型边界**: ground_access 的 equatorial-pass 近似对近极轨 SSO 不区分站纬度,
   只能做高度权衡, 不能做站址对比 (要真星下点轨迹需 sgp4/astropy).

## 复现

```bash
.venv/Scripts/python.exe research_sso_remote_sensing.py
.venv/Scripts/python.exe research_q5_suntransit.py
.venv/Scripts/python.exe research_fleet_energy.py      # 集群能源: 4 配置对比
.venv/Scripts/python.exe research_raan_granularity.py  # RAAN 粒度 × 相位因子 F 扫描
.venv/Scripts/python.exe research_raan_robust.py       # F=1 深谷的稳健性检查
```

---

# 集群能源 (fleet_energy) —— 从单星日影到星座级电力可用性

`src/orbitsim/fleet_energy.py` 把日影判断升级为瞬时 3D 向量判据
(圆柱地影: 背日侧且横向距日地轴 < RE), 与 `orbit_sun` 闭式解互为积分/微分关系,
由 `tests/test_fleet_energy.py` 验证一致 (5/5).

## 文件

| 文件 | 内容 |
|---|---|
| `fleet_energy.png` | 4 种 24 星配置 (单壳/面数加倍/高度异构/相位异构) 全年光照对比 |
| `raan_granularity.png` | 面数 × F 扫描: 低谷平台 + F=1 同步崩溃 |
| `fleet_[A-D].csv` | 各配置逐日 min/mean/max 光照星数 |

## 核心规律 (24 星, 全年 365 天 × 96 槽/天)

1. **低谷深度与面数几乎无关**: F≥2 时 2-24 面都在 14-15/24 平台;
   1 面×24 星靠面内相位冗余 (大数定律) 也有 15 —— 假说"面越多越好"被数据推翻.
2. **Walker 相位因子 F 是集群能源参数**: 每面 1 星 + F=1 时 RAAN≡u 相位锁定,
   全群同步进影, 最深低谷崩到 6/24, 日均低谷 7.1; F≥2 即恢复平台.
   这是真实 Walker δ 星座 (Starlink 等) 选 F>1 的一个少被提及的能源理由.
3. **总量处处相同 (~17.7/24), 分布由结构决定**: 平均光照不敏感,
   敏感的是"最坏时刻保证" —— 集群调度该看 lit_min 而非 lit_mean.
4. **固定星数下异构拆壳是能源负资产**: 两壳各 2 面 (RAAN 覆盖变稀)
   最深低谷 12-14 < 单壳 4 面的 15; 异构的价值在覆盖/分辨率, 不在能源.
5. 单壳的 RAAN 网格让各面光照状态天然去相关 —— 不存在"全晨昏星座",
   任何时刻都有面在晨昏 (全亮) 有面在正午 (深影), 这是集群电力稳定的根源.
