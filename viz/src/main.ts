// orbitsim scenarios (public/scenarios/*.json) as orbits, satellites and inter-satellite links on
// the globe, with local-time, equator and Sun guides. Positions come from scenario.ts, the
// closed-form port of orbitsim (circular orbits, J2 RAAN drift, mean Sun, cylindrical umbra).

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
  HorizontalOrigin,
  ImageryLayer,
  JulianDate,
  LabelStyle,
  Matrix3,
  Matrix4,
  NearFarScalar,
  PolylineArrowMaterialProperty,
  PolylineDashMaterialProperty,
  PolylineGlowMaterialProperty,
  ReferenceFrame,
  type Scene,
  TileMapServiceImageryProvider,
  VerticalOrigin,
  Viewer,
} from "cesium";

import {
  betaOverYear,
  declinationDeg,
  dynamicLinks,
  equatorAtLocalTime,
  equatorRing,
  formatHour,
  gmst,
  type Link,
  localTimeMeridian,
  onDay,
  orbitRing,
  parallel,
  planeGeometry,
  type Scenario,
  type ScenarioSatellite,
  shadowArc,
  siteEcef,
  snapshot,
  staticLinks,
  subsolarLonDeg,
  sunEcef,
  terminator,
  umbraMinutes,
  type Vec3,
} from "./scenario";

/** One per cluster, in the order clusters first appear. */
const CLUSTER_COLORS = [
  "#60a5fa",
  "#f59e0b",
  "#34d399",
  "#f472b6",
  "#a78bfa",
  "#f87171",
  "#22d3ee",
  "#facc15",
  "#fb923c",
];
const RS_COLOR = Color.fromCssColorString("#ffffff");
const RS_OUTLINE = Color.fromCssColorString("#f43f5e");
/** By the link kinds export_satvis.py writes. */
const LINK_COLORS: Record<string, Color> = {
  intra: Color.fromCssColorString("#22d3ee"),
  inter: Color.fromCssColorString("#facc15"),
  rs: Color.fromCssColorString("#f43f5e"),
};
/** A satellite in the umbra. */
const SHADOW_COLOR = Color.fromCssColorString("#475569");
/** Dynamic links one satellite can hold at most, for sizing the polyline pool. */
const DYNAMIC_LINKS_PER_SATELLITE = 4;

const viewer = new Viewer("cesiumContainer", {
  animation: true,
  timeline: true,
  // Cesium's bundled Natural Earth tiles: offline, no ion token.
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
// The scene's Sun is the real one at the epoch, within a few degrees of the mean Sun the umbra
// test uses (equation of time), so the terminator on the globe and the grey points agree.
viewer.scene.globe.enableLighting = true;
viewer.clock.multiplier = 60;
viewer.clock.clockRange = ClockRange.LOOP_STOP;

const ui = {
  select: document.getElementById("scenario") as HTMLSelectElement,
  title: document.getElementById("title")!,
  desc: document.getElementById("desc")!,
  stats: document.getElementById("stats")!,
  orbits: document.getElementById("showOrbits") as HTMLInputElement,
  labels: document.getElementById("showLabels") as HTMLInputElement,
  inertial: document.getElementById("inertial") as HTMLInputElement,
  localTime: document.getElementById("showLocalTime") as HTMLInputElement,
  planes: document.getElementById("showPlanes") as HTMLInputElement,
  shadow: document.getElementById("showShadow") as HTMLInputElement,
  sun: document.getElementById("showSun") as HTMLInputElement,
  equator: document.getElementById("showEquator") as HTMLInputElement,
  subsolar: document.getElementById("showSubsolar") as HTMLInputElement,
  planeTable: document.getElementById("planeTable")!,
  mode: document.getElementById("mode") as HTMLSelectElement,
  keyPoints: document.getElementById("keyPoints")!,
  day: document.getElementById("day") as HTMLInputElement,
  dayLabel: document.getElementById("dayLabel")!,
  dayPresets: document.getElementById("dayPresets")!,
  betaChart: document.getElementById("betaChart") as HTMLCanvasElement,
  betaLegend: document.getElementById("betaLegend")!,
};

/** Local mean solar times the guide meridians mark. */
const GUIDE_HOURS = [0, 6, 10.5, 12, 13.5, 18];
const GUIDE_COLORS: Record<number, string> = {
  0: "#64748b",
  6: "#fb923c",
  10.5: "#38bdf8",
  12: "#fde047",
  13.5: "#a78bfa",
  18: "#fb923c",
};
const GUIDE_NAMES: Record<number, string> = {
  0: "子夜",
  6: "晨",
  10.5: "上午星",
  12: "正午",
  13.5: "下午星",
  18: "昏",
};
/** The umbra arc on an orbit. */
const SHADOW_ARC_COLOR = Color.fromCssColorString("#0f172a");
const EQUATOR_COLOR = Color.fromCssColorString("#e2e8f0");
const TERMINATOR_COLOR = Color.fromCssColorString("#fbbf24");
const SUBSOLAR_COLOR = Color.fromCssColorString("#fde047");
const TROPIC_COLOR = Color.fromCssColorString("#f97316");
/** Days the presets jump to: equinoxes and solstices (day 0 = 1 Jan). */
const SEASON_DAYS: [string, number][] = [
  ["春分", 79],
  ["夏至", 171],
  ["秋分", 265],
  ["冬至", 354],
];

/** The scenario on screen. */
interface Loaded {
  sc: Scenario;
  epoch: JulianDate;
  statics: Link[];
  sats: Entity[];
  orbits: Entity[];
  /** Guides, by the checkbox that shows them. */
  guides: {
    localTime: Entity[];
    planes: Entity[];
    shadow: Entity[];
    sun: Entity[];
    equator: Entity[];
    subsolar: Entity[];
  };
  /** The frame state every callback of one frame shares, recomputed once per clock time. */
  frame: { t: number; ecef: Vec3[]; lit: boolean[]; dyn: Link[] };
}

let loaded: Loaded | undefined;

/**
 * Concise mode, the default, keeps what answers "where is the Sun, how is each plane turned to it,
 * where does each orbit lose sunlight": terminator, Sun arrow, subsolar point, the equator with its
 * 0/6/12/18 h ticks and one LTAN spoke per plane, the umbra arcs. Detail mode adds the rest.
 */
let detail = new URLSearchParams(location.search).get("m") === "detail";
/** Guide entities drawn in detail mode only. */
const detailOnly = new WeakSet<Entity>();

function detailEntity(e: Entity): Entity {
  detailOnly.add(e);
  return e;
}

/**
 * The planes concise mode marks on the globe: the remote-sensing satellites' when the scenario has
 * any, since there they are what the compute constellation is chosen around; otherwise every plane.
 */
function isFocusPlane(sc: Scenario, s: ScenarioSatellite): boolean {
  return s.role === "rs" || !sc.satellites.some((x) => x.role === "rs");
}

/** Local times whose meridians concise mode keeps: noon, and the dawn and dusk sides. */
function keyHour(h: number, e: Entity): Entity {
  return h === 6 || h === 12 || h === 18 ? e : detailEntity(e);
}

function cartesian(p: Vec3): Cartesian3 {
  return new Cartesian3(p[0], p[1], p[2]);
}

function seconds(l: Loaded, time: JulianDate): number {
  return JulianDate.secondsDifference(time, l.epoch);
}

function frameAt(l: Loaded, time: JulianDate): Loaded["frame"] {
  const t = seconds(l, time);
  if (t !== l.frame.t) {
    const snap = snapshot(l.sc, t);
    l.frame = { t, ecef: snap.ecef, lit: snap.lit, dyn: dynamicLinks(l.sc, snap) };
  }
  return l.frame;
}

function linkAt(l: Loaded, k: number, time: JulianDate): Link | undefined {
  const f = frameAt(l, time);
  return k < l.statics.length ? l.statics[k] : f.dyn[k - l.statics.length];
}

function positionProperty(l: Loaded, i: number): CallbackPositionProperty {
  return new CallbackPositionProperty(
    (time) => (time ? cartesian(frameAt(l, time).ecef[i]!) : undefined),
    false,
    ReferenceFrame.FIXED,
  );
}

function colorProperty(l: Loaded, i: number, base: Color): CallbackProperty {
  return new CallbackProperty(
    (time) => (time && !frameAt(l, time).lit[i] ? SHADOW_COLOR : base),
    false,
  );
}

function orbitProperty(l: Loaded, i: number): CallbackProperty {
  let cacheT = Number.NaN;
  let cache: Cartesian3[] = [];
  return new CallbackProperty((time) => {
    if (!time) {
      return cache;
    }
    const t = seconds(l, time);
    // The ring turns with the Earth; 20 s of rotation is under 0.1°.
    if (!(Math.abs(t - cacheT) < 20)) {
      cacheT = t;
      cache = orbitRing(l.sc.satellites[i]!, l.sc.epoch_doy, t).map(cartesian);
    }
    return cache;
  }, false);
}

function linkPositions(l: Loaded, k: number): CallbackProperty {
  return new CallbackProperty((time) => {
    const link = time && linkAt(l, k, time);
    return link ? [cartesian(l.frame.ecef[link.i]!), cartesian(l.frame.ecef[link.j]!)] : [];
  }, false);
}

function linkMaterial(l: Loaded, k: number): PolylineGlowMaterialProperty {
  return new PolylineGlowMaterialProperty({
    glowPower: 0.25,
    color: new CallbackProperty((time) => {
      const link = time && linkAt(l, k, time);
      if (!link) {
        return Color.TRANSPARENT;
      }
      const c = LINK_COLORS[link.kind] ?? Color.WHITE;
      // A shadowed end cannot serve compute: the link is dimmed, not hidden. Concise mode fades the
      // fixed constellation grid so the remote-sensing links, the ones that change, stand out.
      const faded =
        !detail && k < l.statics.length
          ? l.sc.satellites.some((x) => x.role === "rs")
            ? 0
            : 0.4
          : 1;
      const lit = l.frame.lit[link.i] && l.frame.lit[link.j];
      return c.withAlpha(faded * (lit ? 1 : 0.3));
    }, false),
  });
}

/** The scenario as exported, before it is moved to the slider's day. */
let raw: Scenario | undefined;

async function load(name: string): Promise<void> {
  raw = (await (await fetch(`scenarios/${name}.json`)).json()) as Scenario;
  ui.day.value = String(Math.round(raw.epoch_doy));
  show(raw, raw.epoch_doy);
  frameCamera(raw.epoch_doy);
}

/**
 * Looks at the equator at local time 14:00, between noon and dusk, so the subsolar point and the
 * evening terminator are both in view; then turns the view left so the globe sits to the right of
 * the panel, which covers the left ~400 px. Synchronous: `flyHome(0)` finishes a frame later and
 * would undo the turn.
 */
function frameCamera(doy: number): void {
  // Local 14:00: noon (the subsolar point, the Sun arrow) sits inside the disc, dusk on the right.
  const lon = subsolarLonDeg(doy, 0) + 30;
  viewer.camera.setView({ destination: Cartesian3.fromDegrees(lon, 15, 2.3e7) });
  const panel = document.getElementById("panel");
  const w = viewer.canvas.clientWidth;
  if (!panel || w < 900) {
    return;
  }
  const shift = (panel.offsetLeft + panel.offsetWidth) / 2;
  const fov = (viewer.camera.frustum as unknown as { fov: number }).fov;
  // fov spans the wider side; the turn is the angle `shift` pixels subtend at the screen centre.
  viewer.camera.lookLeft(Math.atan((2 * shift * Math.tan(fov / 2)) / w));
}

/** Draws the scenario on day `doy`: the planes carried on by their J2 drift, the Sun at that day. */
function show(base: Scenario, doy: number): void {
  const sc = onDay(base, doy);
  viewer.entities.removeAll();
  const epoch = JulianDate.addDays(
    JulianDate.fromIso8601(base.epoch_iso),
    doy - base.epoch_doy,
    new JulianDate(),
  );
  updateDayLabel(doy);
  const l: Loaded = {
    sc,
    epoch,
    statics: staticLinks(sc),
    sats: [],
    orbits: [],
    guides: { localTime: [], planes: [], shadow: [], sun: [], equator: [], subsolar: [] },
    frame: { t: Number.NaN, ecef: [], lit: [], dyn: [] },
  };
  loaded = l;

  viewer.clock.startTime = epoch.clone();
  viewer.clock.stopTime = JulianDate.addSeconds(epoch, sc.duration_s, new JulianDate());
  viewer.clock.currentTime = epoch.clone();
  viewer.timeline.zoomTo(viewer.clock.startTime, viewer.clock.stopTime);
  ui.title.textContent = sc.title;
  ui.desc.textContent = sc.description;

  const clusters = [...new Set(sc.satellites.filter((s) => s.role !== "rs").map((s) => s.cluster))];
  sc.satellites.forEach((s, i) => {
    const rs = s.role === "rs";
    const base = rs
      ? RS_COLOR
      : Color.fromCssColorString(
          CLUSTER_COLORS[clusters.indexOf(s.cluster) % CLUSTER_COLORS.length]!,
        );
    l.sats.push(
      viewer.entities.add({
        name: s.name,
        description:
          `${rs ? "遥感星" : "算力星"} · ${s.cluster}<br>` +
          `高度 ${(s.alt_m / 1e3).toFixed(0)} km · 倾角 ${s.inc_deg.toFixed(2)}°` +
          (s.ltan_h !== null ? ` · LTAN ${s.ltan_h} h` : "") +
          `<br>周期 ${(360 / s.n_deg_s / 60).toFixed(1)} min`,
        position: positionProperty(l, i),
        point: {
          pixelSize: rs ? 11 : 8,
          color: colorProperty(l, i, base),
          outlineColor: rs ? RS_OUTLINE : Color.BLACK,
          outlineWidth: rs ? 3 : 1,
        },
        label: {
          text: s.name,
          font: "12px sans-serif",
          style: LabelStyle.FILL_AND_OUTLINE,
          outlineWidth: 2,
          verticalOrigin: VerticalOrigin.BOTTOM,
          pixelOffset: new Cartesian2(0, -10),
          translucencyByDistance: new NearFarScalar(2e6, 1, 4e7, 0),
          show: ui.labels.checked,
        },
      }),
    );
    l.orbits.push(
      viewer.entities.add({
        show: ui.orbits.checked && (detail || isPlaneLeader(sc, i)),
        polyline: {
          positions: orbitProperty(l, i),
          width: rs ? 1.6 : 1,
          material: base.withAlpha(rs ? 0.8 : 0.45),
          arcType: ArcType.NONE,
        },
      }),
    );
  });

  const pool = l.statics.length + sc.satellites.length * DYNAMIC_LINKS_PER_SATELLITE;
  for (let k = 0; k < pool; k++) {
    viewer.entities.add({
      polyline: {
        positions: linkPositions(l, k),
        width: 3,
        material: linkMaterial(l, k),
        arcType: ArcType.NONE,
      },
    });
  }

  for (const st of sc.stations) {
    viewer.entities.add({
      name: st.name,
      position: cartesian(siteEcef(st.lat, st.lon)),
      point: { pixelSize: 7, color: RS_OUTLINE },
      label: {
        text: st.name,
        font: "12px sans-serif",
        style: LabelStyle.FILL_AND_OUTLINE,
        outlineWidth: 2,
        pixelOffset: new Cartesian2(0, -12),
      },
    });
  }
  addGuides(l, clusters);
  addSubsolarGuides(l);
  applyGuideVisibility(l);
  drawBetaChart(base, doy, clusters);
}

function updateDayLabel(doy: number): void {
  const date = new Date(Date.UTC(2026, 0, 1 + Math.round(doy)));
  const dec = declinationDeg(doy);
  ui.dayLabel.textContent = `第 ${Math.round(doy)} 天 (${date.getUTCMonth() + 1} 月 ${date.getUTCDate()} 日) · 太阳直射 ${Math.abs(dec).toFixed(1)}°${dec >= 0 ? "N" : "S"}`;
}

/** Longitude [deg] of the subsolar point. */
function sunLon(doy: number, t: number): number {
  const p = sunEcef(doy, t);
  return (Math.atan2(p[1], p[0]) * 180) / Math.PI;
}

/**
 * The subsolar point (the Sun overhead: local time 12:00, latitude = declination), its track for
 * the day along that parallel, and the two tropics it moves between over the year.
 */
function addSubsolarGuides(l: Loaded): void {
  const doy = l.sc.epoch_doy;
  const dec = declinationDeg(doy);
  const at = (time: JulianDate | undefined) => (time ? seconds(l, time) : 0);
  l.guides.subsolar.push(
    viewer.entities.add({
      position: new CallbackPositionProperty(
        (time) => {
          const p = sunEcef(doy, at(time));
          const r = 6378135 + 30e3;
          return new Cartesian3(p[0] * r, p[1] * r, p[2] * r);
        },
        false,
        ReferenceFrame.FIXED,
      ),
      point: {
        pixelSize: 14,
        color: SUBSOLAR_COLOR,
        outlineColor: Color.fromCssColorString("#b45309"),
        outlineWidth: 2,
      },
      label: {
        text: `太阳直射点 ${Math.abs(dec).toFixed(1)}°${dec >= 0 ? "N" : "S"}\n(当地 12:00)`,
        font: "13px sans-serif",
        fillColor: SUBSOLAR_COLOR,
        style: LabelStyle.FILL_AND_OUTLINE,
        outlineWidth: 3,
        showBackground: true,
        backgroundColor: Color.fromCssColorString("#0b0d12").withAlpha(0.7),
        pixelOffset: new Cartesian2(-16, 0),
        horizontalOrigin: HorizontalOrigin.RIGHT,
      },
    }),
    // Its path today: the Sun moves west along the declination parallel, one turn a day.
    viewer.entities.add({
      polyline: {
        positions: parallel(dec, 25e3).map(cartesian),
        width: 2,
        material: new PolylineDashMaterialProperty({ color: SUBSOLAR_COLOR, dashLength: 10 }),
        arcType: ArcType.NONE,
      },
    }),
  );
  const tropics: [number, string][] = [
    [23.44, "北回归线 23.44°N (夏至直射)"],
    [-23.44, "南回归线 23.44°S (冬至直射)"],
  ];
  for (const [lat, name] of tropics) {
    l.guides.subsolar.push(
      detailEntity(
        viewer.entities.add({
          polyline: {
            positions: parallel(lat, 20e3).map(cartesian),
            width: 1.5,
            material: TROPIC_COLOR.withAlpha(0.7),
            arcType: ArcType.NONE,
          },
        }),
      ),
      detailEntity(
        viewer.entities.add({
          position: new CallbackPositionProperty(
            (time) => cartesian(siteEcef(lat, sunLon(doy, at(time)) + 40, 20e3)),
            false,
            ReferenceFrame.FIXED,
          ),
          label: {
            text: name,
            font: "11px sans-serif",
            fillColor: TROPIC_COLOR,
            style: LabelStyle.FILL_AND_OUTLINE,
            outlineWidth: 3,
          },
        }),
      ),
    );
  }
}

/** β over the year for each plane, with the day on screen marked: how the seasons change the umbra. */
function drawBetaChart(base: Scenario, doy: number, clusters: string[]): void {
  const cv = ui.betaChart;
  const ctx = cv.getContext("2d");
  if (!ctx) {
    return;
  }
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth;
  const h = cv.clientHeight;
  cv.width = w * dpr;
  cv.height = h * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const pad = { l: 30, r: 6, t: 6, b: 16 };
  const x = (d: number) => pad.l + ((w - pad.l - pad.r) * d) / 365;
  const y = (b: number) => pad.t + ((h - pad.t - pad.b) * (90 - b)) / 180;
  ctx.font = "10px sans-serif";
  ctx.strokeStyle = "#2c313b";
  ctx.fillStyle = "#9aa1ad";
  for (const b of [-90, -45, 0, 45, 90]) {
    ctx.beginPath();
    ctx.moveTo(pad.l, y(b));
    ctx.lineTo(w - pad.r, y(b));
    ctx.stroke();
    ctx.fillText(`${b}°`, 2, y(b) + 3);
  }
  // The no-umbra bands |β| ≥ asin(RE/r), at the first satellite's altitude.
  const thr = (Math.asin(6378135 / (6378135 + base.satellites[0]!.alt_m)) * 180) / Math.PI;
  ctx.fillStyle = "rgba(250, 204, 21, 0.10)";
  ctx.fillRect(pad.l, y(90), w - pad.l - pad.r, y(thr) - y(90));
  ctx.fillRect(pad.l, y(-thr), w - pad.l - pad.r, y(-90) - y(-thr));
  ctx.fillStyle = "#facc15";
  ctx.fillText(`|β| ≥ ${thr.toFixed(0)}° 不进地影`, pad.l + 4, y(thr) - 3);
  ctx.fillStyle = "#64748b";
  for (const [name, d] of SEASON_DAYS) {
    ctx.fillText(name, x(d) - 10, h - 3);
  }
  // Daily: a 53° plane's β cycles in ≈66 days, which 5-day samples alias into a sawtooth.
  const days = Array.from({ length: 365 }, (_, k) => k);
  const legend: string[] = [];
  const leaders = planeLeaders(base);
  // Concise mode: a non-SSO shell is one shaded band (its planes' β envelope), not a line per plane.
  const shells = new Map<string, PlaneLeader[]>();
  if (!detail) {
    for (const p of leaders.filter((x) => !isSso(x.s) && x.s.role !== "rs")) {
      const key = `${p.s.inc_deg.toFixed(1)}|${p.s.alt_m}`;
      shells.set(key, [...(shells.get(key) ?? []), p]);
    }
    for (const ps of shells.values()) {
      const curves = ps.map((p) => betaOverYear(base, p.s, days));
      const lo = days.map((_, k) => Math.min(...curves.map((c) => c[k]!)));
      const hi = days.map((_, k) => Math.max(...curves.map((c) => c[k]!)));
      const color = planeColor(ps[0]!.s, clusters);
      ctx.fillStyle = color.withAlpha(0.25).toCssColorString();
      ctx.beginPath();
      hi.forEach((b, k) => (k ? ctx.lineTo(x(days[k]!), y(b)) : ctx.moveTo(x(days[k]!), y(b))));
      for (let k = lo.length - 1; k >= 0; k--) {
        ctx.lineTo(x(days[k]!), y(lo[k]!));
      }
      ctx.closePath();
      ctx.fill();
      const nows = ps.map((p) => betaOverYear(base, p.s, [doy])[0]!);
      const umbras = ps.map((p, k) => umbraMinutes(p.s, nows[k]!));
      legend.push(
        `<li><i style="background:${color.toCssColorString()}"></i>${ps.length} 个 ${ps[0]!.s.inc_deg.toFixed(0)}° 面 (阴影带): β ${Math.min(...nows).toFixed(0)}…${Math.max(...nows).toFixed(0)}° · 地影 ${Math.min(...umbras).toFixed(0)}–${Math.max(...umbras).toFixed(0)} min/圈</li>`,
      );
    }
  }
  const banded = new Set([...shells.values()].flat());
  leaders
    .filter((p) => !banded.has(p))
    .forEach(({ s, members }) => {
      const color = planeColor(s, clusters).toCssColorString();
      const betas = betaOverYear(base, s, days);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      betas.forEach((b, k) => (k ? ctx.lineTo(x(days[k]!), y(b)) : ctx.moveTo(x(days[k]!), y(b))));
      ctx.stroke();
      const now = betaOverYear(base, s, [doy])[0]!;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x(doy), y(now), 3.5, 0, 2 * Math.PI);
      ctx.fill();
      // In HTML below the chart: labels on the canvas overlap where planes share a β.
      legend.push(
        `<li><i style="background:${color}"></i>${members.join(" + ")}: β ${now.toFixed(0)}° · 地影 ${umbraMinutes(s, now).toFixed(0)} min/圈</li>`,
      );
    });
  ctx.strokeStyle = "#e2e8f0";
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(x(doy), pad.t);
  ctx.lineTo(x(doy), h - pad.b);
  ctx.stroke();
  ctx.setLineDash([]);
  ui.betaLegend.innerHTML = legend.join("");
}

/** One orbit plane: its first satellite, and every cluster (or RS satellite) flying in it. */
interface PlaneLeader {
  s: ScenarioSatellite;
  i: number;
  members: string[];
}

/** One entry per distinct (RAAN, inclination, altitude). */
function planeLeaders(sc: Scenario): PlaneLeader[] {
  const byKey = new Map<string, PlaneLeader>();
  sc.satellites.forEach((s, i) => {
    const key = `${s.raan0_deg.toFixed(2)}|${s.inc_deg.toFixed(2)}|${s.alt_m}`;
    const member = s.role === "rs" ? s.name : s.cluster;
    const p = byKey.get(key);
    if (!p) {
      byKey.set(key, { s, i, members: [member] });
    } else if (!p.members.includes(member)) {
      p.members.push(member);
    }
  });
  return [...byKey.values()];
}

/** Hours between two local times on a 24 h circle. */
function hourGap(a: number, b: number): number {
  const d = Math.abs(a - b) % 24;
  return Math.min(d, 24 - d);
}

/** Whether the plane follows the Sun: its J2 drift within 2% of the mean solar motion. */
function isSso(s: ScenarioSatellite): boolean {
  return Math.abs(s.raan_rate_deg_s * 86400 - 0.9856) < 0.02;
}

/**
 * What a plane's LTAN means for its sunlight. Only for a sun-synchronous plane is it a fixed
 * orientation; any other plane drifts through every local time, so today's value is a snapshot.
 */
function planeKind(ltanH: number, s?: ScenarioSatellite): string {
  if (s && !isSso(s)) {
    const days = 360 / Math.abs(s.raan_rate_deg_s * 86400 - 0.9856);
    return `非太阳同步 (LTAN 每 ${days.toFixed(0)} 天转一圈), 今天`;
  }
  if (Math.min(hourGap(ltanH, 6), hourGap(ltanH, 18)) <= 1) {
    return "晨昏: 侧对太阳, 少/无地影";
  }
  if (Math.min(hourGap(ltanH, 12), hourGap(ltanH, 0)) <= 1) {
    return "正午/子夜: 正对太阳, 地影最长";
  }
  return ltanH < 12 ? "上午: 适合光学成像" : "下午: 适合光学成像";
}

/** A property recomputed when the clock moves more than `stepS`, which guides tolerate. */
function cached<T>(l: Loaded, stepS: number, compute: (t: number) => T): CallbackProperty {
  let at = Number.NaN;
  let value: T;
  return new CallbackProperty((time) => {
    const t = time ? seconds(l, time) : 0;
    if (!(Math.abs(t - at) < stepS)) {
      at = t;
      value = compute(t);
    }
    return value;
  }, false);
}

function addGuides(l: Loaded, clusters: string[]): void {
  const { sc } = l;
  const doy = sc.epoch_doy;

  // Local-time meridians: the Earth turns under them, they stay fixed relative to the Sun.
  for (const h of GUIDE_HOURS) {
    const color = Color.fromCssColorString(GUIDE_COLORS[h]!);
    l.guides.localTime.push(
      keyHour(
        h,
        viewer.entities.add({
          polyline: {
            positions: cached(l, 30, (t) => localTimeMeridian(doy, t, h, 60e3).map(cartesian)),
            width: h === 12 || h === 0 ? 2 : 1.5,
            material: color.withAlpha(0.85),
            arcType: ArcType.NONE,
          },
        }),
      ),
      detailEntity(
        viewer.entities.add({
          position: new CallbackPositionProperty(
            (time) =>
              cartesian(localTimeMeridian(doy, time ? seconds(l, time) : 0, h, 60e3, 60)[17]!),
            false,
            ReferenceFrame.FIXED,
          ),
          label: {
            text: `${formatHour(h)} ${GUIDE_NAMES[h]}`,
            font: "13px sans-serif",
            fillColor: color,
            style: LabelStyle.FILL_AND_OUTLINE,
            outlineWidth: 3,
            showBackground: true,
            backgroundColor: Color.fromCssColorString("#0b0d12").withAlpha(0.7),
            verticalOrigin: VerticalOrigin.CENTER,
          },
        }),
      ),
    );
  }

  // The terminator, drawn just above the surface, and an arrow toward the Sun.
  l.guides.sun.push(
    viewer.entities.add({
      polyline: {
        positions: cached(l, 30, (t) => terminator(doy, t).map(cartesian)),
        width: 2.5,
        material: TERMINATOR_COLOR.withAlpha(0.9),
        arcType: ArcType.NONE,
      },
    }),
    viewer.entities.add({
      polyline: {
        positions: cached(l, 30, (t) => {
          const s = sunEcef(doy, t);
          const a = 1.02 * 6378135;
          const b = 2.1 * 6378135;
          return [
            cartesian([s[0] * a, s[1] * a, s[2] * a]),
            cartesian([s[0] * b, s[1] * b, s[2] * b]),
          ];
        }),
        width: 12,
        material: new PolylineArrowMaterialProperty(Color.fromCssColorString("#fde047")),
        arcType: ArcType.NONE,
      },
    }),
    detailEntity(
      viewer.entities.add({
        position: new CallbackPositionProperty(
          (time) => {
            const s = sunEcef(doy, time ? seconds(l, time) : 0);
            const r = 2.25 * 6378135;
            return new Cartesian3(s[0] * r, s[1] * r, s[2] * r);
          },
          false,
          ReferenceFrame.FIXED,
        ),
        label: {
          text: "☀ 太阳方向",
          font: "15px sans-serif",
          fillColor: Color.fromCssColorString("#fde047"),
          style: LabelStyle.FILL_AND_OUTLINE,
          outlineWidth: 3,
        },
      }),
    ),
  );

  // Each orbit plane: its umbra arc and an ascending-node marker labelled with LTAN and β.
  const leaders = planeLeaders(sc);
  addEquatorGuides(l, leaders, clusters);
  for (const { s, members } of leaders) {
    const color = planeColor(s, clusters);
    l.guides.shadow.push(
      viewer.entities.add({
        polyline: {
          positions: cached(l, 20, (t) => shadowArc(s, doy, t).map(cartesian)),
          width: 6,
          material: SHADOW_ARC_COLOR.withAlpha(0.85),
          arcType: ArcType.NONE,
        },
      }),
    );
    const focus = (e: Entity) => (isFocusPlane(sc, s) ? e : detailEntity(e));
    l.guides.planes.push(
      focus(
        viewer.entities.add({
          position: new CallbackPositionProperty(
            (time) => cartesian(planeGeometry(s, doy, time ? seconds(l, time) : 0).node),
            false,
            ReferenceFrame.FIXED,
          ),
          point: { pixelSize: 9, color: Color.TRANSPARENT, outlineColor: color, outlineWidth: 2.5 },
          label: {
            text: new CallbackProperty((time) => {
              const g = planeGeometry(s, doy, time ? seconds(l, time) : 0);
              return detail
                ? `升交点 ${members.join(" + ")}\nLTAN ${formatHour(g.ltanH)} · β ${g.betaDeg.toFixed(0)}°`
                : `${members.join(" + ")}  LTAN ${formatHour(g.ltanH)}`;
            }, false),
            font: "12px sans-serif",
            fillColor: color,
            style: LabelStyle.FILL_AND_OUTLINE,
            outlineWidth: 3,
            showBackground: true,
            backgroundColor: Color.fromCssColorString("#0b0d12").withAlpha(0.7),
            pixelOffset: new Cartesian2(14, 0),
            horizontalOrigin: HorizontalOrigin.LEFT,
          },
        }),
      ),
    );
  }
  renderPlaneTable(l, leaders);
}

function planeColor(s: ScenarioSatellite, clusters: string[]): Color {
  return s.role === "rs"
    ? RS_OUTLINE
    : Color.fromCssColorString(
        CLUSTER_COLORS[clusters.indexOf(s.cluster) % CLUSTER_COLORS.length]!,
      );
}

/**
 * The equator and what LTAN reads off it: a 24 h local-time dial around the equator, fixed to the
 * Sun, and for each plane the two points where it crosses the equator (the nodes), joined by the
 * line of nodes through the Earth. LTAN is the dial reading under the ascending node.
 */
function addEquatorGuides(l: Loaded, leaders: PlaneLeader[], clusters: string[]): void {
  const doy = l.sc.epoch_doy;
  const at = (time: JulianDate | undefined) => (time ? seconds(l, time) : 0);
  const DIAL_ALT = 40e3;
  const DIAL_NAMES: Record<number, string> = { 0: "子夜", 6: "晨", 12: "正午", 18: "昏" };
  l.guides.equator.push(
    viewer.entities.add({
      polyline: {
        positions: equatorRing(DIAL_ALT).map(cartesian),
        width: 2.5,
        material: EQUATOR_COLOR.withAlpha(0.9),
        arcType: ArcType.NONE,
      },
    }),
  );
  // The dial: a tick each hour, labelled every 3 h; concise mode keeps 0/6/12/18 h.
  for (let h = 0; h < 24; h += 1) {
    const major = h % 3 === 0;
    const key = h % 6 === 0;
    const tick = viewer.entities.add({
      position: new CallbackPositionProperty(
        (time) => cartesian(equatorAtLocalTime(doy, at(time), h, DIAL_ALT)),
        false,
        ReferenceFrame.FIXED,
      ),
      point: { pixelSize: key ? 7 : major ? 5 : 3, color: EQUATOR_COLOR },
      label: major
        ? {
            text: key
              ? `${String(h).padStart(2, "0")}h ${DIAL_NAMES[h]}`
              : `${String(h).padStart(2, "0")}h`,
            font: key ? "12px sans-serif" : "11px sans-serif",
            fillColor: EQUATOR_COLOR,
            style: LabelStyle.FILL_AND_OUTLINE,
            outlineWidth: 3,
            pixelOffset: new Cartesian2(0, 14),
          }
        : undefined,
    });
    l.guides.equator.push(key ? tick : detailEntity(tick));
  }
  for (const { s, members } of leaders) {
    const color = planeColor(s, clusters);
    const geom = (time: JulianDate | undefined) => planeGeometry(s, doy, at(time));
    l.guides.equator.push(
      // The line of nodes: the orbit plane meets the equator plane along it.
      detailEntity(
        viewer.entities.add({
          polyline: {
            positions: new CallbackProperty((time) => {
              const g = geom(time);
              return [cartesian(g.node), cartesian(g.descNode)];
            }, false),
            width: 1.5,
            material: new PolylineDashMaterialProperty({
              color: color.withAlpha(0.9),
              dashLength: 14,
            }),
            arcType: ArcType.NONE,
          },
        }),
      ),
      detailEntity(
        viewer.entities.add({
          position: new CallbackPositionProperty(
            (time) => cartesian(geom(time).descNode),
            false,
            ReferenceFrame.FIXED,
          ),
          point: { pixelSize: 8, color: Color.TRANSPARENT, outlineColor: color, outlineWidth: 2 },
          label: {
            text: new CallbackProperty(
              (time) =>
                `降交点 ${members.join(" + ")}\n地方时 ${formatHour((geom(time).ltanH + 12) % 24)} (= LTAN + 12h)`,
              false,
            ),
            font: "11px sans-serif",
            fillColor: color.withAlpha(0.85),
            style: LabelStyle.FILL_AND_OUTLINE,
            outlineWidth: 3,
            pixelOffset: new Cartesian2(14, 0),
            horizontalOrigin: HorizontalOrigin.LEFT,
          },
        }),
      ),
      // A spoke from the dial up to the ascending node, so the reading is visible.
      (isFocusPlane(l.sc, s) ? (e: Entity) => e : detailEntity)(
        viewer.entities.add({
          polyline: {
            positions: new CallbackProperty((time) => {
              const g = geom(time);
              return [
                cartesian(equatorAtLocalTime(doy, at(time), g.ltanH, DIAL_ALT)),
                cartesian(g.node),
              ];
            }, false),
            width: 3,
            material: color,
            arcType: ArcType.NONE,
          },
        }),
      ),
    );
  }
}

/** The panel's table: what each plane's LTAN means for sunlight. */
function renderPlaneTable(l: Loaded, leaders: PlaneLeader[]): void {
  const rows = leaders.map(({ s, members }) => {
    const g = planeGeometry(s, l.sc.epoch_doy, 0);
    const shadowMin = umbraMinutes(s, g.betaDeg);
    const name = members.join(" + ");
    return `<tr><td>${name}</td><td>${formatHour(g.ltanH)}</td><td>${g.betaDeg.toFixed(0)}°</td><td>${shadowMin.toFixed(0)} min</td><td>${planeKind(g.ltanH, s)}</td></tr>`;
  });
  ui.planeTable.innerHTML = `<table><thead><tr><th>轨道面</th><th>LTAN</th><th>β</th><th>每圈地影</th><th>类型</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

function applyGuideVisibility(l: Loaded): void {
  const set = (es: Entity[], on: boolean) =>
    es.forEach((e) => (e.show = on && (detail || !detailOnly.has(e))));
  set(l.guides.localTime, ui.localTime.checked);
  set(l.guides.planes, ui.planes.checked);
  set(l.guides.shadow, ui.shadow.checked);
  set(l.guides.sun, ui.sun.checked);
  set(l.guides.equator, ui.equator.checked);
  set(l.guides.subsolar, ui.subsolar.checked);
  renderKeyPoints(l);
  viewer.scene.requestRender();
}

/** Whether satellite `i` is the first of its orbit plane, the one concise mode draws the orbit of. */
function isPlaneLeader(sc: Scenario, i: number): boolean {
  return planeLeaders(sc).some((p) => p.i === i);
}

function applyOrbitVisibility(l: Loaded): void {
  l.orbits.forEach((e, i) => (e.show = ui.orbits.checked && (detail || isPlaneLeader(l.sc, i))));
  viewer.scene.requestRender();
}

/**
 * The panel's "key points": per plane, one line on what its LTAN and today's β mean, ranked so the
 * planes that differ most come first.
 */
function renderKeyPoints(l: Loaded): void {
  const doy = l.sc.epoch_doy;
  const rows = planeLeaders(l.sc).map(({ s, members }) => {
    const g = planeGeometry(s, doy, 0);
    const umbra = umbraMinutes(s, g.betaDeg);
    const period = 360 / s.n_deg_s / 60;
    return { s, members, g, umbra, frac: umbra / period };
  });
  const clusters = [
    ...new Set(l.sc.satellites.filter((x) => x.role !== "rs").map((x) => x.cluster)),
  ];
  // Planes of one constellation are one line: an SSO group by its sunlight, a drifting shell whole.
  const groups = new Map<string, typeof rows>();
  for (const r of rows) {
    const key =
      r.s.role === "rs"
        ? `rs|${r.s.name}`
        : isSso(r.s)
          ? `${planeKind(r.g.ltanH, r.s)}|${Math.round(Math.abs(r.g.betaDeg) / 5)}|${r.s.alt_m}`
          : `drift|${r.s.inc_deg.toFixed(1)}|${r.s.alt_m}`;
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  const items = [...groups.values()].map((g) => {
    const r = g[0]!;
    const color = planeColor(r.s, clusters).toCssColorString();
    const who = g.length === 1 ? r.members.join(" + ") : `${g.length} 个面`;
    if (!isSso(r.s)) {
      const umbras = g.map((x) => x.umbra);
      const betas = g.map((x) => Math.abs(x.g.betaDeg));
      return (
        `<li><i style="background:${color}"></i><b>${who}</b> 倾角 ${r.s.inc_deg.toFixed(0)}° → ${planeKind(r.g.ltanH, r.s)} ` +
        `|β| ${Math.min(...betas).toFixed(0)}–${Math.max(...betas).toFixed(0)}°, 每圈地影 ${Math.min(...umbras).toFixed(0)}–${Math.max(...umbras).toFixed(0)} min</li>`
      );
    }
    const sunlight =
      r.umbra === 0
        ? "全程光照"
        : `每圈 ${r.umbra.toFixed(0)} min 地影 (${(r.frac * 100).toFixed(0)}%)`;
    const ltans = g.map((x) => formatHour(x.g.ltanH)).join(" / ");
    return `<li><i style="background:${color}"></i><b>${who}</b> LTAN ${ltans} → ${planeKind(r.g.ltanH, r.s)}; |β| ${Math.abs(r.g.betaDeg).toFixed(0)}°, ${sunlight}</li>`;
  });
  const lit = rows.filter((r) => r.umbra === 0).length;
  const dec = declinationDeg(doy);
  const head =
    `<li class="kp-head">太阳直射 ${Math.abs(dec).toFixed(1)}°${dec >= 0 ? "N" : "S"} · ` +
    `${rows.length} 个轨道面里 ${lit} 个不进地影</li>`;
  ui.keyPoints.innerHTML = head + items.join("");
}

function updateStats(): void {
  if (!loaded) {
    return;
  }
  const f = frameAt(loaded, viewer.clock.currentTime);
  const kinds = new Map<string, number>();
  for (const link of [...loaded.statics, ...f.dyn]) {
    kinds.set(link.kind, (kinds.get(link.kind) ?? 0) + 1);
  }
  const names: Record<string, string> = { intra: "簇内", inter: "簇间", rs: "遥感→算力" };
  const links = [...kinds].map(([k, v]) => `${names[k] ?? k} ${v}`).join(" · ");
  ui.stats.textContent = `t = ${(f.t / 60).toFixed(1)} min · 光照 ${f.lit.filter(Boolean).length}/${f.lit.length} · 链路 ${links || "0"}`;
}

/**
 * Locks the camera to orbitsim's inertial frame, which turns with its own Greenwich angle
 * rather than Cesium's ICRF: the orbit planes stand still and the Earth turns under them.
 */
function inertialCamera(_scene: Scene, time: JulianDate): void {
  if (!loaded) {
    return;
  }
  const toFixed = Matrix3.fromRotationZ(-gmst(loaded.sc.epoch_doy, seconds(loaded, time)));
  const offset = Cartesian3.clone(viewer.camera.position);
  viewer.camera.lookAtTransform(Matrix4.fromRotationTranslation(toFixed), offset);
}

viewer.clock.onTick.addEventListener(updateStats);
ui.orbits.addEventListener("change", () => loaded && applyOrbitVisibility(loaded));
ui.labels.addEventListener("change", () => {
  for (const e of loaded?.sats ?? []) {
    if (e.label) {
      e.label.show = new CallbackProperty(() => ui.labels.checked, true);
    }
  }
});
for (const box of [ui.localTime, ui.planes, ui.shadow, ui.sun, ui.equator, ui.subsolar]) {
  box.addEventListener("change", () => loaded && applyGuideVisibility(loaded));
}
ui.inertial.addEventListener("change", () => {
  viewer.scene.postUpdate.removeEventListener(inertialCamera);
  if (ui.inertial.checked) {
    viewer.scene.postUpdate.addEventListener(inertialCamera);
  } else {
    viewer.camera.lookAtTransform(Matrix4.IDENTITY);
  }
});

async function main(): Promise<void> {
  const index = (await (await fetch("scenarios/index.json")).json()) as {
    name: string;
    title: string;
    satellites: number;
  }[];
  for (const s of index) {
    const o = document.createElement("option");
    o.value = s.name;
    o.textContent = `${s.title} (${s.satellites} 星)`;
    ui.select.append(o);
  }
  const wanted = new URLSearchParams(location.search).get("s");
  ui.select.value = index.find((s) => s.name === wanted)?.name ?? index[0]!.name;
  ui.select.addEventListener("change", () => {
    history.replaceState(null, "", `?s=${ui.select.value}${detail ? "&m=detail" : ""}`);
    void load(ui.select.value);
  });
  for (const [name, d] of SEASON_DAYS) {
    const b = document.createElement("button");
    b.textContent = name;
    b.addEventListener("click", () => {
      ui.day.value = String(d);
      ui.day.dispatchEvent(new Event("input"));
    });
    ui.dayPresets.append(b);
  }
  ui.day.addEventListener("input", () => raw && show(raw, Number(ui.day.value)));
  ui.mode.value = detail ? "detail" : "concise";
  ui.mode.addEventListener("change", () => {
    detail = ui.mode.value === "detail";
    const q = new URLSearchParams(location.search);
    if (detail) {
      q.set("m", "detail");
    } else {
      q.delete("m");
    }
    history.replaceState(null, "", `?${q}`);
    // Labels carry their mode in their text, so the scene is rebuilt rather than toggled.
    if (raw) {
      show(raw, Number(ui.day.value));
    }
  });
  await load(ui.select.value);
}

void main();
