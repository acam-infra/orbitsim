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

---

# 地影逃逸 (shadow_escape) —— 迁移判据的几何输入

`src/orbitsim/shadow_escape.py`: 影弧闭式 (中心 u_s+180°, 半宽 w = arccos(√(r²−RE²)/(r cos β))),
给出每颗星的剩余光照/剩余影时; 在 +Grid ISL 图上算到最近亮星的跳数, 以及带容量 k 的贪心卸载.
`tests/test_shadow_escape.py` 验证闭式与 `lit_mask` 逐点一致 (5/5).

复现: `.venv/Scripts/python.exe research_shadow_escape.py` (约 10 s) → `shadow_escape.png`、`shadow_escape.csv`、`migrate_vs_wait.csv`.
采样: 25 天 (每 15 天) × 每天 48 时刻, 550 km.

## 核心规律

1. **"跨 3–4 个面才能逃出地影"在 LAB-1687 规模不成立.** 4×4 F1 SSO 下 100% 的进影星 1 跳内就有亮星,
   每颗亮星只接 1 颗影星 (k=1) 时也全部 1 跳. 邻居同影比例 0.28, 远不是"整片同相".
2. **同相是 F=1 + 密星座的现象.** 邻面同号星同在影的比例: 6×8 F1 0.44 → F3 0.03; 12×12 F1 0.69 → F5 0.00.
   F≥2 时所有配置 100% 1 跳逃逸. 只有 F=1 且面数多 (12×12, 24×22) 才出现 2–3 跳, k=1 时最多 4–5 跳.
   这与 fleet_energy 的 "F=1 同步进影" 是同一个机制.
3. **星历放置大多能替代运行中迁移.** 到达时 ≤1 跳内找得到剩余光照 ≥ L 的星:
   4×4 F1 下 L=20 min 为 99%, L=40 min 为 90%; F≥2 的配置 L=20 min 全为 100%.
   LAB-1687 长任务寿命约 3–9 min (6k–18k tok × ~30 ms). 也就是说, 只要地影是唯一的断电源,
   "预知星历的到达放置"这个基线几乎可以把地影引起的迁移需求消掉 —— C2 必须正面对比它.
4. **迁移 vs 等待差两个数量级.** 剩余影时均值约 16 min; 12k token (1.6 GB) KV 走 2 跳:
   10 Gbps 1.4 s, 4 Gbps (扣 6 Gbps 背景) 3.3 s, 1 Gbps 13 s. 对地影这种分钟级断电, 迁移总是比等待便宜,
   判据真正起作用的是**秒级、不可预知**的断电 (OrbitWeaver 36–122 s 窗口) 和带宽被数传吃掉的时段.

## 对 claim 的含义

- C1/C2 如果以地影为主要扰动, 审稿人用"星历放置 + F≥2"就能推翻: 地影可预知, 而且邻星基本都亮.
- 迁移的必要性要落在: (a) 不可预知事件 (过热断电, 载荷开机); (b) 寿命长于剩余光照的请求 (L ≥ 20–40 min 的 agentic 会话);
  (c) F=1 的密星座. 判据图的横轴建议用 "请求剩余寿命 / 剩余光照" 和 "KV 传输时间 / 剩余影时".
- 局限: 只算地影, 不含数传/载荷/热事件; +Grid 静态拓扑; 不含亮星的显存余量 (k 只是代理).
