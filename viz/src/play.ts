// Co-simulation playback: orbitsim positions + satsim network events on one clock.
// The satellites move by the same closed form as the geometry viewer (scenario.ts); links appear
// only while the contact trace says they are up; colours, widths and arrows come from the satsim
// recording (public/playback/<name>.json, written by `satsim-cosim --viz`).

import "cesium/Build/Cesium/Widgets/widgets.css";
import {
  ArcType,
  buildModuleUrl,
  CallbackPositionProperty,
  CallbackProperty,
  Cartesian2,
  Cartesian3,
  ClockRange,
  Color,
  type Entity,
  ImageryLayer,
  JulianDate,
  LabelStyle,
  NearFarScalar,
  PolylineArrowMaterialProperty,
  PolylineGlowMaterialProperty,
  ReferenceFrame,
  TileMapServiceImageryProvider,
  VerticalOrigin,
  Viewer,
} from "cesium";

import {
  activeEvents,
  curveAt,
  frameAt as playFrameAt,
  heat,
  isUp,
  lowerBound,
  type Playback,
  type PlayEvent,
  type PlayFrame,
  type PlayRun,
  POLICY_COLORS,
  POLICY_NAMES,
  SHOW_S,
} from "./playback";
import { type Scenario, snapshot, subsolarLonDeg, type Vec3 } from "./scenario";

const LINK_COLORS: Record<string, Color> = {
  intra: Color.fromCssColorString("#22d3ee"),
  inter: Color.fromCssColorString("#facc15"),
  rs: Color.fromCssColorString("#f43f5e"),
};
const BUSY = Color.fromCssColorString("#fb923c");
const EVENT_COLORS: Record<string, Color> = {
  upload: Color.fromCssColorString("#4ade80"),
  deliver: Color.fromCssColorString("#93c5fd"),
  mig: Color.fromCssColorString("#fb923c"),
  mig_abort: Color.fromCssColorString("#ef4444"),
  cut: Color.fromCssColorString("#ef4444"),
  lost: Color.fromCssColorString("#ef4444"),
};
const EVENT_POOL = 120;
const SPEEDS = [30, 60, 120, 300];

const viewer = new Viewer("cesiumContainer", {
  animation: true,
  timeline: true,
  baseLayer: ImageryLayer.fromProviderAsync(
    TileMapServiceImageryProvider.fromUrl(buildModuleUrl("Assets/Textures/NaturalEarthII")),
  ),
  baseLayerPicker: false,
  geocoder: false,
  homeButton: false,
  infoBox: true,
  navigationHelpButton: false,
  sceneModePicker: false,
  selectionIndicator: true,
});
viewer.scene.globe.enableLighting = true;
viewer.clock.multiplier = 60;
viewer.clock.clockRange = ClockRange.LOOP_STOP;

const ui = {
  playback: document.getElementById("playback") as HTMLSelectElement,
  policy: document.getElementById("policy") as HTMLSelectElement,
  title: document.getElementById("title")!,
  desc: document.getElementById("desc")!,
  speed: document.getElementById("speed")!,
  live: document.getElementById("live")!,
  table: document.getElementById("table")!,
  chart: document.getElementById("chart") as HTMLCanvasElement,
  ticker: document.getElementById("ticker")!,
};

interface State {
  pb: Playback;
  sc: Scenario;
  run: PlayRun;
  policy: string;
  epoch: JulianDate;
  names: string[];
  rsSet: Set<number>;
  frame: {
    t: number;
    ecef: Vec3[];
    lit: boolean[];
    pf: PlayFrame | undefined;
    rate: Map<number, number>;
    up: boolean[];
    events: PlayEvent[];
  };
}

let st: State | undefined;

function cart(p: Vec3): Cartesian3 {
  return new Cartesian3(p[0], p[1], p[2]);
}

function frame(s: State, time: JulianDate): State["frame"] {
  const t = Math.max(0, JulianDate.secondsDifference(time, s.epoch));
  if (t !== s.frame.t) {
    const snap = snapshot(s.sc, t);
    const pf = playFrameAt(s.run, s.pb.frame_s, t);
    s.frame = {
      t,
      ecef: snap.ecef,
      lit: snap.lit,
      pf,
      rate: new Map((pf?.e ?? []).map(([e, g]) => [e, g])),
      up: s.pb.trace.edges.map((e) => isUp(e.up, t)),
      events: activeEvents(s.run.events, t, EVENT_POOL),
    };
  }
  return s.frame;
}

function isDark(s: State, j: number, t: number): boolean {
  return isUp(s.pb.trace.dark[j] ?? [], t);
}

// -- entities ---------------------------------------------------------------------------------
function addSatellites(s: State): void {
  s.sc.satellites.forEach((sat: { name: string; role: string }, i: number) => {
    const rs = sat.role === "rs";
    viewer.entities.add({
      id: `sat-${i}`,
      name: sat.name,
      description: rs ? "遥感星: 提交推理请求, 结果要回到它" : "算力星",
      position: new CallbackPositionProperty(
        (time) => (time ? cart(frame(s, time).ecef[i]!) : undefined),
        false,
        ReferenceFrame.FIXED,
      ),
      point: {
        pixelSize: new CallbackProperty((time) => {
          if (rs || !time) {
            return rs ? 12 : 6;
          }
          const load = frame(s, time).pf?.load[i] ?? 0;
          return Math.min(20, 6 + 1.4 * load);
        }, false),
        color: new CallbackProperty((time) => {
          if (rs || !time) {
            return Color.WHITE;
          }
          const f = frame(s, time);
          const [r, g, b] = heat(f.pf?.kv[i] ?? 0);
          const c = Color.fromBytes(r, g, b, 255);
          const load = f.pf?.load[i] ?? 0;
          const dark = isDark(s, i, f.t);
          if (load === 0) {
            return (dark ? Color.fromCssColorString("#1e293b") : Color.fromCssColorString("#475569")).withAlpha(0.9);
          }
          return dark ? Color.lerp(c, Color.fromCssColorString("#0f172a"), 0.55, new Color()) : c;
        }, false),
        outlineColor: new CallbackProperty((time) => {
          if (rs) {
            return Color.fromCssColorString("#f43f5e");
          }
          return time && isDark(s, i, frame(s, time).t) ? Color.fromCssColorString("#64748b") : Color.BLACK;
        }, false),
        outlineWidth: rs ? 3 : 1.5,
      },
      label: rs
        ? {
            text: sat.name,
            font: "12px sans-serif",
            style: LabelStyle.FILL_AND_OUTLINE,
            outlineWidth: 2,
            verticalOrigin: VerticalOrigin.BOTTOM,
            pixelOffset: new Cartesian2(0, -12),
            translucencyByDistance: new NearFarScalar(2e6, 1, 5e7, 0.6),
          }
        : undefined,
    });
  });
}

function addLinks(s: State): void {
  const cap = s.pb.link_gbps;
  s.pb.trace.edges.forEach((e, k) => {
    const base = LINK_COLORS[e.kind] ?? Color.WHITE;
    const util = (time: JulianDate | undefined) => {
      if (!time) {
        return 0;
      }
      const g = frame(s, time).rate.get(k) ?? 0;
      return Math.min(1, g / (cap[e.kind] ?? 10));
    };
    viewer.entities.add({
      polyline: {
        show: new CallbackProperty((time) => (time ? frame(s, time).up[k]! : false), false),
        positions: new CallbackProperty((time) => {
          if (!time) {
            return [];
          }
          const f = frame(s, time);
          return [cart(f.ecef[e.u]!), cart(f.ecef[e.v]!)];
        }, false),
        width: new CallbackProperty((time) => 1.2 + 6 * util(time), false),
        material: new PolylineGlowMaterialProperty({
          glowPower: new CallbackProperty((time) => 0.12 + 0.3 * util(time), false),
          color: new CallbackProperty((time) => {
            const u = util(time);
            if (u > 0) {
              return Color.lerp(base, BUSY, Math.min(1, 0.4 + u), new Color()).withAlpha(0.95);
            }
            return base.withAlpha(e.kind === "intra" ? 0.28 : 0.55);
          }, false),
        }),
        arcType: ArcType.NONE,
      },
    });
  });
}

/** Path of an event as node indices. */
function eventPath(ev: PlayEvent): number[] {
  const d = ev[2];
  if (Array.isArray(d.path)) {
    return d.path as number[];
  }
  if (typeof d.src === "number" && typeof d.dst === "number") {
    return [d.src, d.dst];
  }
  if (typeof d.node === "number") {
    return [d.node as number];
  }
  return [];
}

function addEventPool(s: State): void {
  for (let k = 0; k < EVENT_POOL; k++) {
    const evAt = (time: JulianDate | undefined) => (time ? frame(s, time).events[k] : undefined);
    viewer.entities.add({
      polyline: {
        show: new CallbackProperty((time) => {
          const ev = evAt(time);
          return !!ev && eventPath(ev).length > 1;
        }, false),
        positions: new CallbackProperty((time) => {
          const ev = evAt(time);
          if (!ev || !time) {
            return [];
          }
          const f = frame(s, time);
          // lift the arrow a little above the link so both stay visible
          return eventPath(ev).map((j) => Cartesian3.multiplyByScalar(cart(f.ecef[j]!), 1.012, new Cartesian3()));
        }, false),
        width: new CallbackProperty((time) => {
          const ev = evAt(time);
          return ev && (ev[1] === "mig" || ev[1] === "mig_abort") ? 7 : 3.5;
        }, false),
        material: new PolylineArrowMaterialProperty(
          new CallbackProperty((time) => {
            const ev = evAt(time);
            if (!ev || !time) {
              return Color.TRANSPARENT;
            }
            const age = (frame(s, time).t - ev[0]) / (SHOW_S[ev[1]] ?? 1);
            return (EVENT_COLORS[ev[1]] ?? Color.WHITE).withAlpha(Math.max(0.15, 1 - age * 0.85));
          }, false),
        ),
        arcType: ArcType.NONE,
      },
    });
    // a dot travelling along migrations, a ring on cuts / losses
    viewer.entities.add({
      position: new CallbackPositionProperty(
        (time) => {
          const ev = evAt(time);
          if (!ev || !time) {
            return undefined;
          }
          const f = frame(s, time);
          const p = eventPath(ev);
          if (!p.length) {
            return undefined;
          }
          if (ev[1] !== "mig" || p.length < 2) {
            return Cartesian3.multiplyByScalar(cart(f.ecef[p[p.length - 1]!]!), 1.012, new Cartesian3());
          }
          const prog = Math.min(1, (f.t - ev[0]) / (SHOW_S.mig! * 0.6));
          const seg = prog * (p.length - 1);
          const a = Math.min(p.length - 2, Math.floor(seg));
          const pa = cart(f.ecef[p[a]!]!);
          const pb = cart(f.ecef[p[a + 1]!]!);
          const out = Cartesian3.lerp(pa, pb, seg - a, new Cartesian3());
          return Cartesian3.multiplyByScalar(out, 1.012, out);
        },
        false,
        ReferenceFrame.FIXED,
      ),
      point: {
        show: new CallbackProperty((time) => {
          const ev = evAt(time);
          return !!ev && ["mig", "mig_abort", "cut", "lost"].includes(ev[1]);
        }, false),
        pixelSize: new CallbackProperty((time) => {
          const ev = evAt(time);
          return ev && ev[1] === "mig" ? 10 : 16;
        }, false),
        color: new CallbackProperty((time) => {
          const ev = evAt(time);
          if (!ev) {
            return Color.TRANSPARENT;
          }
          return ev[1] === "mig" ? Color.fromCssColorString("#fed7aa") : Color.TRANSPARENT;
        }, false),
        outlineColor: new CallbackProperty((time) => {
          const ev = evAt(time);
          return ev ? (EVENT_COLORS[ev[1]] ?? Color.WHITE) : Color.TRANSPARENT;
        }, false),
        outlineWidth: 3,
      },
    });
  }
}

// -- panel ------------------------------------------------------------------------------------
const fmtT = (t: number) => {
  const m = Math.floor(t / 60);
  return `${String(Math.floor(m / 60)).padStart(1, "0")}:${String(m % 60).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
};

function renderTable(s: State): void {
  const cols: [string, string, (v: number | null) => string][] = [
    ["good_long_frac", "长任务达标", (v) => (v == null ? "-" : `${(v * 100).toFixed(1)}%`)],
    ["good_frac", "全部达标", (v) => (v == null ? "-" : `${(v * 100).toFixed(1)}%`)],
    ["lat_long_p90_s", "长任务 p90", (v) => (v == null ? "-" : `${(v / 60).toFixed(1)}m`)],
    ["dark_tok_share", "影内解码", (v) => (v == null ? "-" : `${(v * 100).toFixed(1)}%`)],
    ["migrations", "迁移", (v) => (v == null ? "-" : v.toFixed(0))],
  ];
  let html = "<table><tr><th>策略</th>" + cols.map((c) => `<th>${c[1]}</th>`).join("") + "</tr>";
  for (const p of s.pb.policies) {
    const row = s.pb.mean[p] ?? {};
    html +=
      `<tr class="${p === s.policy ? "cur" : ""}"><td><i class="dot" style="background:${POLICY_COLORS[p] ?? "#fff"}"></i>${POLICY_NAMES[p] ?? p}</td>` +
      cols.map(([k, , f]) => `<td>${f((row[k] as number | null) ?? null)}</td>`).join("") +
      "</tr>";
  }
  ui.table.innerHTML = html + "</table>";
}

function drawChart(s: State, t: number): void {
  const c = ui.chart;
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (c.width !== w * dpr) {
    c.width = w * dpr;
    c.height = h * dpr;
  }
  const g = c.getContext("2d")!;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  const base = s.pb.runs.greedy?.good_curve;
  const T = s.pb.trace.horizon_s;
  const series = s.pb.policies.map((p) => {
    const cur = s.pb.runs[p]!.good_curve;
    return { p, pts: cur.map(([tt, v], k) => [tt, base ? v - (base[k]?.[1] ?? 0) : v] as [number, number]) };
  });
  let lo = 0;
  let hi = 1;
  for (const sr of series) {
    for (const [, v] of sr.pts) {
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
  }
  const pad = { l: 34, r: 8, t: 8, b: 18 };
  const X = (tt: number) => pad.l + ((w - pad.l - pad.r) * tt) / T;
  const Y = (v: number) => pad.t + ((h - pad.t - pad.b) * (hi - v)) / (hi - lo || 1);
  g.strokeStyle = "#334155";
  g.lineWidth = 1;
  g.beginPath();
  g.moveTo(pad.l, Y(0));
  g.lineTo(w - pad.r, Y(0));
  g.stroke();
  g.fillStyle = "#94a3b8";
  g.font = "10px sans-serif";
  g.fillText(`+${hi}`, 2, Y(hi) + 8);
  g.fillText("0", 2, Y(0) + 3);
  if (lo < 0) {
    g.fillText(`${lo}`, 2, Y(lo));
  }
  for (let hh = 0; hh <= T / 3600; hh++) {
    g.fillText(`${hh}h`, X(hh * 3600) - 6, h - 4);
  }
  for (const sr of series) {
    g.strokeStyle = POLICY_COLORS[sr.p] ?? "#fff";
    g.lineWidth = sr.p === s.policy ? 2.5 : 1.3;
    g.beginPath();
    sr.pts.forEach(([tt, v], k) => (k ? g.lineTo(X(tt), Y(v)) : g.moveTo(X(tt), Y(v))));
    g.stroke();
  }
  g.strokeStyle = "#e2e8f0";
  g.setLineDash([3, 3]);
  g.beginPath();
  g.moveTo(X(t), pad.t);
  g.lineTo(X(t), h - pad.b);
  g.stroke();
  g.setLineDash([]);
}

const KIND_TEXT: Record<string, [string, string]> = {
  mig: ["迁移", "k-mig"],
  mig_done: ["迁移完成", "k-mig"],
  mig_abort: ["迁移中止", "k-abort"],
  cut: ["断链打断传输", "k-cut"],
  lost: ["结果无法回传", "k-lost"],
};

function renderTicker(s: State, t: number): void {
  const ev = s.run.events;
  const out: string[] = [];
  for (let k = lowerBound(ev, t + 1e-9) - 1, n = 0; k >= 0 && out.length < 9 && n < 6000; k--, n++) {
    const [tt, kind, d] = ev[k]!;
    const kt = KIND_TEXT[kind];
    if (!kt) {
      continue;
    }
    const name = (j: unknown) => (typeof j === "number" ? s.names[j] : "?");
    let what = `请求 #${d.req}`;
    if (kind === "mig") {
      what += ` ${name(d.src)} → ${name(d.dst)} · ${(d.GB as number).toFixed(2)} GB · ${(d.path as number[]).length - 1} 跳`;
    } else if (kind === "mig_done" || kind === "mig_abort") {
      what += ` ${name(d.src)} → ${name(d.dst)}`;
    } else if (kind === "cut") {
      what = `${d.tag === "mig" ? "KV 迁移" : "上传"} · 请求 #${d.req}`;
    } else if (kind === "lost") {
      what += ` 在 ${name(d.node)}`;
    }
    out.push(`<li class="${kt[1]}">${fmtT(tt)} ${kt[0]} · ${what}</li>`);
  }
  ui.ticker.innerHTML = out.join("") || '<li class="note">还没有</li>';
}

function renderLive(s: State, t: number): void {
  const f = frame(s, viewer.clock.currentTime);
  const comp = s.sc.satellites.map((_: unknown, i: number) => i).filter((i: number) => !s.rsSet.has(i));
  const decoding = comp.reduce((a: number, i: number) => a + (f.pf?.load[i] ?? 0), 0);
  const dark = comp.filter((i: number) => isDark(s, i, t)).length;
  const up = f.up.filter(Boolean).length;
  const migs = f.events.filter((e) => e[1] === "mig").length;
  const good = curveAt(s.run.good_curve, t);
  const cells: [string, string][] = [
    [fmtT(t), "仿真时刻"],
    [String(decoding), "在解码的请求"],
    [`${dark}/${comp.length}`, "地影中的算力星"],
    [String(up), "在线链路"],
    [String(migs), "近 1 分钟迁移"],
    [String(good), "累计达标交付"],
  ];
  ui.live.innerHTML = cells.map(([v, k]) => `<div><b>${v}</b><span>${k}</span></div>`).join("");
}

let lastPanel = 0;
viewer.clock.onTick.addEventListener((clock) => {
  if (!st) {
    return;
  }
  const now = performance.now();
  if (now - lastPanel < 250) {
    return;
  }
  lastPanel = now;
  const t = Math.max(0, JulianDate.secondsDifference(clock.currentTime, st.epoch));
  renderLive(st, t);
  renderTicker(st, t);
  drawChart(st, t);
});

viewer.selectedEntityChanged.addEventListener((e: Entity | undefined) => {
  if (!st || !e || typeof e.id !== "string" || !e.id.startsWith("sat-")) {
    return;
  }
  const i = Number(e.id.slice(4));
  const t = Math.max(0, JulianDate.secondsDifference(viewer.clock.currentTime, st.epoch));
  const f = frame(st, viewer.clock.currentTime);
  const dark = st.pb.trace.dark[i] ?? [];
  const next = dark.find(([, b]) => b > t);
  const shadow = next ? (next[0] <= t ? `在地影中, ${fmtT(next[1])} 出影` : `${fmtT(next[0])} 进影`) : "本时段不再进影";
  e.description = new CallbackProperty(
    () =>
      st!.rsSet.has(i)
        ? `遥感星 ${st!.names[i]}: 提交请求, 结果要经星间链路回到它`
        : `算力星 ${st!.names[i]}<br>在跑请求 ${f.pf?.load[i] ?? 0} · 显存 ${(100 * (f.pf?.kv[i] ?? 0)).toFixed(0)}%<br>${shadow}`,
    true,
  ) as unknown as typeof e.description;
});

// -- loading ----------------------------------------------------------------------------------
const cache = new Map<string, Playback>();

async function fetchPlayback(name: string): Promise<Playback> {
  let pb = cache.get(name);
  if (!pb) {
    pb = (await (await fetch(`playback/${name}.json`)).json()) as Playback;
    cache.set(name, pb);
  }
  return pb;
}

function frameCamera(s: State): void {
  const lon = subsolarLonDeg(s.sc.epoch_doy, 0) + 40;
  viewer.camera.setView({ destination: Cartesian3.fromDegrees(lon, 20, 2.4e7) });
  const panel = document.getElementById("panel");
  const w = viewer.canvas.clientWidth;
  if (panel && w > 900) {
    const fov = (viewer.camera.frustum as unknown as { fov: number }).fov;
    const shift = (panel.offsetLeft + panel.offsetWidth) / 2;
    viewer.camera.lookLeft(Math.atan((2 * shift * Math.tan(fov / 2)) / w));
  }
}

async function show(name: string, policy?: string, keepTime = false): Promise<void> {
  const pb = await fetchPlayback(name);
  const pol = policy && pb.runs[policy] ? policy : (pb.policies.includes("contact_aware") ? "contact_aware" : pb.policies[0]!);
  const prevT = st && keepTime ? JulianDate.secondsDifference(viewer.clock.currentTime, st.epoch) : 0;
  viewer.entities.removeAll();
  const sc = pb.scenario as Scenario;
  const epoch = JulianDate.fromIso8601(sc.epoch_iso);
  const s: State = {
    pb,
    sc,
    run: pb.runs[pol]!,
    policy: pol,
    epoch,
    names: pb.trace.nodes.map((n) => n.name),
    rsSet: new Set(pb.trace.nodes.filter((n) => n.role === "rs").map((n) => n.id)),
    frame: { t: Number.NaN, ecef: [], lit: [], pf: undefined, rate: new Map(), up: [], events: [] },
  };
  st = s;
  ui.title.textContent = pb.title;
  ui.desc.textContent = pb.description;
  ui.policy.innerHTML = pb.policies.map((p) => `<option value="${p}">${POLICY_NAMES[p] ?? p}</option>`).join("");
  ui.policy.value = pol;
  addLinks(s);
  addEventPool(s);
  addSatellites(s);
  viewer.clock.startTime = epoch.clone();
  viewer.clock.stopTime = JulianDate.addSeconds(epoch, pb.trace.horizon_s, new JulianDate());
  viewer.clock.currentTime = JulianDate.addSeconds(epoch, prevT, new JulianDate());
  viewer.timeline.zoomTo(viewer.clock.startTime, viewer.clock.stopTime);
  renderTable(s);
  if (!keepTime) {
    frameCamera(s);
  }
  const q = new URLSearchParams(location.search);
  q.set("p", name);
  q.set("pol", pol);
  history.replaceState(null, "", `?${q}`);
}

function renderSpeed(): void {
  ui.speed.innerHTML = "倍速 " + SPEEDS.map((v) => `<button data-v="${v}" class="${viewer.clock.multiplier === v ? "on" : ""}">${v}×</button>`).join("");
  ui.speed.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => {
      viewer.clock.multiplier = Number(b.dataset.v);
      viewer.clock.shouldAnimate = true;
      renderSpeed();
    }),
  );
}

async function main(): Promise<void> {
  const index = (await (await fetch("playback/index.json")).json()) as { name: string; title: string }[];
  ui.playback.innerHTML = index.map((e) => `<option value="${e.name}">${e.title}</option>`).join("");
  const q = new URLSearchParams(location.search);
  const first = q.get("p") && index.some((e) => e.name === q.get("p")) ? q.get("p")! : index[0]!.name;
  ui.playback.value = first;
  ui.playback.addEventListener("change", () => void show(ui.playback.value));
  ui.policy.addEventListener("change", () => void show(ui.playback.value, ui.policy.value, true));
  renderSpeed();
  viewer.clock.shouldAnimate = true;
  await show(first, q.get("pol") ?? undefined);
  const t0 = Number(q.get("t"));
  if (st && t0 > 0) {
    viewer.clock.currentTime = JulianDate.addSeconds(st.epoch, t0, new JulianDate());
  }
}

void main();
