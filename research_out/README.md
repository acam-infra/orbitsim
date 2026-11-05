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
```
