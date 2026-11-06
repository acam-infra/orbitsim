"""合成轨道场景: 遥感星 + 算力星 + 地面站, 看"天数天算"在几何上长什么样.

场景 (全部圆轨道, 闭式 + 时间步进, dt=20 s, 每季 2 天):
  遥感星 (RS)
    RS-1030  光学, SSO 500 km, LTAN 10:30 (高分/资源类)
    RS-1330  光学, SSO 500 km, LTAN 13:30 (下午星)
    RS-SAR   SAR,  SSO 600 km, LTAN 06:00 (晨昏 SAR, 昼夜都能成像)
  算力星座 (候选)
    C1 同面伴飞 6 星   与 RS-1030 同轨道面 500 km, 均匀分布
    C2 晨昏面 12 星    SSO 650 km LTAN 06:00 (能源最优, Suncatcher 一类)
    C3 Walker53 6x8    550 km 53°, F=1 (Starlink 风格)
    C4 SSO-Walker 6x8  550 km SSO, RAAN 均布, F=3
  地面站: 密云 / 喀什 / 三亚 (国内) ; 可选 +基律纳 (北极站)
  成像区: 中国大陆外包框 lat 18–53°, lon 73–135°; 光学要求星下点太阳高度角 ≥ 10°.

问题:
  Q1 遥感星一天在国内成像多少分钟、能见国内站多少分钟、成像到落地要等多久 (数据时效)?
  Q2 遥感星任意时刻有没有算力星在视距 (≤ R_ISL) 内? 成像时刻呢? 对端亮不亮?
  Q3 链路多久换一次 (切换频率) —— 决定在轨推理请求要不要跨星迁移.
  Q4 经算力星处理后再落地, 时效能缩短多少?
  Q5 算力星自己的能源: 光照比例, 以及"在视距内且亮"的比例.
"""
from __future__ import annotations

import csv
import os
import statistics as st
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from orbitsim import fleet_synth as fs

OUT = os.path.join(os.path.dirname(__file__), "research_out")
os.makedirs(OUT, exist_ok=True)

DT = 20.0
SPAN = 2 * 86400.0
T = np.arange(0.0, SPAN, DT)
SEASONS = {"春分": 81.0, "夏至": 172.0, "秋分": 264.0, "冬至": 355.0}
R_ISL = 4000e3            # 星间激光链路最大距离
MIN_EL = 5.0              # 地面站最低仰角
SUN_EL_OPT = 10.0
CHINA = (18.0, 53.0, 73.0, 135.0)
STATIONS = {"密云": (40.4, 116.9), "喀什": (39.5, 76.0), "三亚": (18.3, 109.3)}
STATIONS_PLUS = {**STATIONS, "基律纳": (67.9, 21.1)}

RS = [
    fs.make_sat("RS-1030", 500, ltan_h=10.5, role="rs", optical=True),
    fs.make_sat("RS-1330", 500, ltan_h=13.5, role="rs", optical=True, u0_deg=90.0),
    fs.make_sat("RS-SAR", 600, ltan_h=6.0, role="rs", optical=False, u0_deg=45.0),
]
COMPUTE = {
    "C1 同面伴飞6": fs.sso_plane("C1", 6, 500, 10.5, u0_deg=15.0),
    "C2 晨昏面12": fs.sso_plane("C2", 12, 650, 6.0),
    "C3 Walker53 6x8": fs.walker("C3", 6, 8, 550, 53.0, F=1),
    "C4 SSO-Walker 6x8": [
        fs.make_sat(f"C4/p{p}s{k}", 550, ltan_h=(p * 4.0) % 24, u0_deg=360 * k / 8 + 360 * 3 * p / 6,
                    role="compute", plane=p)
        for p in range(6) for k in range(8)],
}


def next_true_time(mask: np.ndarray) -> np.ndarray:
    """For each step, time [s] until mask is next True (0 if True now; inf if never)."""
    out = np.full(mask.shape, np.inf)
    nxt = np.inf
    for i in range(len(mask) - 1, -1, -1):
        if mask[i]:
            nxt = i
        out[i] = (nxt - i) * DT if nxt != np.inf else np.inf
    return out


def station_view(pos, doy, stations):
    vis = np.zeros(pos.shape[:2], dtype=bool)
    for lat, lon in stations.values():
        vis |= fs.elevation_deg(pos, fs.site_eci(lat, lon, doy, T)) >= MIN_EL
    return vis


def first_day(x):
    return x[: int(86400 / DT)]


def analyse(doy: float, stations: dict):
    sun = fs.sun_vec(doy)
    p_rs = fs.positions(RS, doy, T)
    lat, lon = fs.subpoint(p_rs, doy, T)
    sun_el = fs.solar_elevation_deg(lat, lon, doy, T)
    in_cn = (lat >= CHINA[0]) & (lat <= CHINA[1]) & (lon >= CHINA[2]) & (lon <= CHINA[3])
    optical = np.array([s["optical"] for s in RS])[None, :]
    lit_ok = np.where(optical, sun_el >= SUN_EL_OPT, True)
    imaging = in_cn & lit_ok
    # 海外成像: |lat| ≤ 60, 不在国内框 (代表一带一路 / 全球热点, 落地只能靠国内站)
    overseas = (np.abs(lat) <= 60.0) & ~in_cn & lit_ok
    rs_gs = station_view(p_rs, doy, stations)

    rows = []
    for ci, (cname, csats) in enumerate(COMPUTE.items()):
        p_c = fs.positions(csats, doy, T)
        c_lit = fs.lit(p_c, sun)
        c_gs = station_view(p_c, doy, stations)
        rng, clear = fs.los_range(p_rs, p_c)
        link = clear & (rng <= R_ISL)                    # (T, RS, C)
        link_lit = link & c_lit[:, None, :]
        any_gs_c = c_gs.any(axis=1)                       # 星座内任一星见站 (假设星座内 ISL 连通)
        t_c_gs = next_true_time(any_gs_c)
        for ri, rs in enumerate(RS):
            img = imaging[:, ri]
            l_any = link[:, ri, :].any(axis=1)
            l_lit = link_lit[:, ri, :].any(axis=1)
            # 切换: 每步选最近的可达算力星, 统计更换次数
            d = np.where(link[:, ri, :], rng[:, ri, :], np.inf)
            best = np.where(np.isfinite(d.min(axis=1)), d.argmin(axis=1), -1)
            sw = int(np.sum((best[1:] != best[:-1]) & (best[1:] >= 0) & (best[:-1] >= 0)))
            hold = fs.runs(np.r_[best[1:] == best[:-1]] & (best[1:] >= 0), DT)
            # 时效: 成像时刻 → 落地
            t_raw = next_true_time(rs_gs[:, ri])                  # 原始数据等遥感星自己过站
            t_link = next_true_time(l_lit)                        # 等到一颗亮的算力星
            idx = np.arange(len(T))
            j = np.minimum(idx + (np.where(np.isfinite(t_link), t_link, 0) / DT).astype(int), len(T) - 1)
            t_via = np.where(np.isfinite(t_link), t_link + t_c_gs[j], np.inf)  # 处理结果经星座落地
            def lat_stats(sel):
                a = first_day(t_raw)[sel]; b = first_day(t_via)[sel]
                a = a[np.isfinite(a)]; b = b[np.isfinite(b)]
                f = lambda x, q: float(np.percentile(x, q)) / 60 if x.size else float("nan")
                return f(a, 50), f(a, 90), f(b, 50), f(b, 90)
            sel = first_day(img)
            sel_o = first_day(overseas[:, ri])
            r50, r90, v50, v90 = lat_stats(sel)
            o_r50, o_r90, o_v50, o_v90 = lat_stats(sel_o)
            # 单颗算力星的连续接触时长 (粘滞策略的上限: 不换星能连多久)
            contact = []
            for j in range(link.shape[2]):
                contact += fs.runs(link_lit[:, ri, j], DT)
            contact = [c for c in contact if c < SPAN - DT]  # 去掉全程不断的伴飞
            rows.append({
                "rs": rs["name"], "compute": cname, "n_compute": len(csats),
                "img_min_day": first_day(img).sum() * DT / 60,
                "rs_gs_min_day": first_day(rs_gs[:, ri]).sum() * DT / 60,
                "los_frac": first_day(l_any).mean(),
                "los_lit_frac": first_day(l_lit).mean(),
                "img_los_lit_frac": first_day(l_lit)[sel].mean() if sel.any() else float("nan"),
                "switch_per_h": sw / (SPAN / 3600),
                "hold_med_min": (st.median(hold) / 60) if hold else 0.0,
                "lat_raw_med_min": r50, "lat_raw_p90_min": r90,
                "lat_via_med_min": v50, "lat_via_p90_min": v90,
                "ovs_min_day": sel_o.sum() * DT / 60,
                "ovs_raw_med_min": o_r50, "ovs_raw_p90_min": o_r90,
                "ovs_via_med_min": o_v50, "ovs_via_p90_min": o_v90,
                "ovs_los_lit_frac": first_day(l_lit)[sel_o].mean() if sel_o.any() else float("nan"),
                "contact_med_min": (st.median(contact) / 60) if contact else float("inf"),
                "contact_p10_min": (float(np.percentile(contact, 10)) / 60) if contact else float("inf"),
                "c_lit_frac": first_day(c_lit).mean(),
                "c_gs_cover": first_day(any_gs_c).mean(),
            })
    return rows, (lat, lon, imaging, rs_gs)


def main():
    all_rows = []
    tracks = None
    for stname, stations in (("国内3站", STATIONS), ("国内3站+基律纳", STATIONS_PLUS)):
        for season, doy in SEASONS.items():
            rows, tr = analyse(doy, stations)
            for r in rows:
                r["season"], r["stations"] = season, stname
            all_rows += rows
            if tracks is None:
                tracks = (doy, tr)
            print(f"done {stname} {season}", flush=True)

    keys = ["stations", "season"] + [k for k in all_rows[0] if k not in ("stations", "season")]
    with open(os.path.join(OUT, "synth_fleet.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in all_rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})

    # 四季平均
    def agg(stname):
        g = {}
        for r in all_rows:
            if r["stations"] != stname:
                continue
            g.setdefault((r["rs"], r["compute"]), []).append(r)
        out = []
        for (rs, c), rr in g.items():
            m = {k: float(np.nanmean([x[k] for x in rr])) for k in rr[0]
                 if isinstance(rr[0][k], (int, float)) and k != "n_compute"}
            m.update(rs=rs, compute=c, n_compute=rr[0]["n_compute"])
            out.append(m)
        return out

    for stname in ("国内3站", "国内3站+基律纳"):
        print(f"\n===== {stname} (四季平均) =====")
        print(f"{'RS':>8} {'算力星座':>18} {'国内成像':>6} {'海外成像':>6} {'过站':>5} {'视距且亮':>6} "
              f"{'海外可卸':>6} {'切换/h':>6} {'接触中位/p10':>11} {'海外原始 50/90':>14} {'海外经算力 50/90':>15} "
              f"{'算力光照':>6} {'站覆盖':>5}")
        for m in agg(stname):
            print(f"{m['rs']:>8} {m['compute']:>18} {m['img_min_day']:6.0f} {m['ovs_min_day']:6.0f} "
                  f"{m['rs_gs_min_day']:5.0f} {m['los_lit_frac']:6.2f} {m['ovs_los_lit_frac']:6.2f} "
                  f"{m['switch_per_h']:6.1f} {m['contact_med_min']:6.1f}/{m['contact_p10_min']:<5.1f} "
                  f"{m['ovs_raw_med_min']:6.0f}/{m['ovs_raw_p90_min']:<7.0f} "
                  f"{m['ovs_via_med_min']:6.0f}/{m['ovs_via_p90_min']:<8.0f} "
                  f"{m['c_lit_frac']:6.2f} {m['c_gs_cover']:5.2f}")

    # ---------- 图 ----------
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt

    A = agg("国内3站")
    rs_names = [s["name"] for s in RS]
    cn = list(COMPUTE)
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))

    ax = axes[0, 0]
    doy, (lat, lon, imaging, rs_gs) = tracks
    day = slice(0, int(86400 / DT))
    for ri, c in zip(range(3), ["#2563eb", "#f59e0b", "#16a34a"]):
        la, lo = lat[day, ri], lon[day, ri]
        brk = np.where(np.abs(np.diff(lo)) > 180)[0] + 1
        for seg in np.split(np.arange(len(lo)), brk):
            ax.plot(lo[seg], la[seg], color=c, lw=0.5, alpha=0.5)
        im = imaging[day, ri]
        ax.scatter(lo[im], la[im], s=3, color=c, label=f"{rs_names[ri]} 成像")
    for n, (a, b) in STATIONS_PLUS.items():
        ax.plot(b, a, "k^"); ax.annotate(n, (b, a), fontsize=8)
    ax.add_patch(plt.Rectangle((CHINA[2], CHINA[0]), CHINA[3] - CHINA[2], CHINA[1] - CHINA[0],
                               fill=False, ls="--", color="#64748b"))
    ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
    ax.set_title(f"(a) 遥感星 24h 星下点 (doy {doy:.0f}), 粗点 = 国内成像")
    ax.legend(fontsize=8, loc="lower left"); ax.grid(alpha=0.3)

    def mat(key):
        return np.array([[next(m[key] for m in A if m["rs"] == r and m["compute"] == c) for c in cn]
                         for r in rs_names])

    for ax, key, title, fmt in (
        (axes[0, 1], "ovs_los_lit_frac", "(b) 海外成像时刻有亮的算力星在视距内 (可即时卸载)", "{:.2f}"),
        (axes[1, 0], "contact_med_min", "(c) 遥感星-单颗算力星连续接触时长中位数 [min]", "{:.1f}"),
    ):
        M = mat(key)
        imh = ax.imshow(M, cmap="viridis" if key != "switch_per_h" else "magma", aspect="auto")
        ax.set_xticks(range(len(cn))); ax.set_xticklabels(cn, fontsize=8, rotation=15)
        ax.set_yticks(range(3)); ax.set_yticklabels(rs_names)
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                ax.text(j, i, fmt.format(M[i, j]), ha="center", va="center", color="w", fontsize=10)
        ax.set_title(title); fig.colorbar(imh, ax=ax)

    ax = axes[1, 1]
    raw = mat("ovs_raw_med_min")[:, 0]
    via = mat("ovs_via_med_min")
    x = np.arange(3); wbar = 0.16
    ax.bar(x - 2 * wbar, raw, wbar, color="#64748b", label="原始数据等自己过站")
    for j, c in enumerate(cn):
        bx = x + (j - 1) * wbar
        ax.bar(bx, via[:, j], wbar, label=f"经 {c}")
        for xi, v in zip(bx, via[:, j]):
            if v < 0.5:
                ax.annotate("≈0", (xi, 0.05), ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(rs_names)
    ax.set_ylabel("成像→落地 中位时延 [min]"); ax.set_yscale("symlog", linthresh=1); ax.set_title("(d) 海外成像数据时效 (国内 3 站): 星上处理后经算力星座落地")
    ax.legend(fontsize=8); ax.grid(alpha=0.3, axis="y")

    fig.tight_layout()
    png = os.path.join(OUT, "synth_fleet.png")
    fig.savefig(png, dpi=140)
    print(f"\n图: {png}")


if __name__ == "__main__":
    main()
