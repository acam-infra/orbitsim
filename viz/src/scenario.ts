// Closed-form propagation of orbitsim scenarios (orbitsim/export_satvis.py). Cesium-free for
// node-env vitest: the reference positions in each scenario's `check` hold this port to the
// Python model, which is circular, spherical-Earth, J2 secular RAAN drift only, mean Sun.

/** Earth radius orbitsim uses [m]. Not WGS84: the scenarios' altitudes are relative to it. */
export const RE_M = 6378135.0;

const DEG = Math.PI / 180;
const YEAR_DAYS = 365.2422;
const OBLIQUITY = 23.44 * DEG;

/** One circular satellite as export_satvis.py writes it. */
export interface ScenarioSatellite {
  name: string;
  /** "rs" for remote sensing, "compute" for a compute satellite. */
  role: string;
  /** The group a dynamic link rule names. */
  group: string;
  /** Satellites of one cluster share a colour; the different-cluster rule compares it. */
  cluster: string;
  alt_m: number;
  inc_deg: number;
  /** At the epoch, 00:00 UTC of the epoch day. */
  raan0_deg: number;
  raan_rate_deg_s: number;
  /** Argument of latitude at the epoch. */
  u0_deg: number;
  n_deg_s: number;
  ltan_h: number | null;
}

/** A link drawn whenever its two ends see each other, chosen per frame. */
export interface DynamicLinkRule {
  a: string;
  b: string;
  kind: string;
  max_range_m: number;
  grazing_m: number;
  /** Only links between different clusters. */
  different_cluster?: boolean;
  /** One link per `a` satellite, to its nearest eligible `b`. */
  nearest_only?: boolean;
  /** `b` must be sunlit. */
  require_lit_b?: boolean;
}

/** A Python reference point for the port. */
export interface CheckSample {
  sat: string;
  t: number;
  ecef: [number, number, number];
  lit: boolean;
}

export interface Scenario {
  name: string;
  title: string;
  description: string;
  epoch_doy: number;
  epoch_iso: string;
  duration_s: number;
  satellites: ScenarioSatellite[];
  /** Static links are [a, b, kind] by name, drawn always. */
  links: { static: [string, string, string][]; dynamic: DynamicLinkRule[] };
  stations: { name: string; lat: number; lon: number }[];
  check: CheckSample[];
}

export type Vec3 = [number, number, number];

/** Mean-Sun right ascension [rad], vernal equinox at day 81. */
function sunRa(doy: number): number {
  return (2 * Math.PI * (doy - 81)) / YEAR_DAYS;
}

/** Solar declination [deg]: the latitude of the subsolar point, ±23.44° at the solstices. */
export function declinationDeg(doy: number): number {
  return (OBLIQUITY * Math.sin(sunRa(doy))) / DEG;
}

/**
 * The scenario moved to another day of the year. Within a scenario the Sun is held at its day
 * (orbitsim's model); a different day carries every plane on by its J2 drift over the days in
 * between, so an SSO plane keeps its LTAN and a 53° plane regresses ≈5°/day.
 */
export function onDay(sc: Scenario, doy: number): Scenario {
  const days = doy - sc.epoch_doy;
  if (days === 0) {
    return sc;
  }
  const dt = days * 86400;
  return {
    ...sc,
    epoch_doy: doy,
    satellites: sc.satellites.map((s) => ({
      ...s,
      raan0_deg: (((s.raan0_deg + s.raan_rate_deg_s * dt) % 360) + 360) % 360,
      u0_deg: (((s.u0_deg + s.n_deg_s * dt) % 360) + 360) % 360,
    })),
  };
}

/** A parallel of latitude as a closed ring, `alt` above the sphere. */
export function parallel(latDeg: number, alt = 0, steps = 180): Vec3[] {
  const out: Vec3[] = [];
  for (let k = 0; k <= steps; k++) {
    out.push(siteEcef(latDeg, (360 * k) / steps, alt));
  }
  return out;
}

/** β [deg] of a plane on each day of `days`, with the plane carried on by its J2 drift. */
export function betaOverYear(sc: Scenario, s: ScenarioSatellite, days: number[]): number[] {
  return days.map((d) => planeGeometry(onDay({ ...sc, satellites: [s] }, d).satellites[0]!, d, 0).betaDeg);
}

/** Umbra minutes per revolution at β, the closed form `orbit_sun.eclipse_minutes`. */
export function umbraMinutes(s: ScenarioSatellite, betaDeg: number): number {
  const r = RE_M + s.alt_m;
  const c = Math.sqrt(r * r - RE_M * RE_M) / (r * Math.cos(betaDeg * DEG));
  return c < 1 ? ((Math.acos(c) / Math.PI) * 360) / s.n_deg_s / 60 : 0;
}

/** Unit ECI vector toward the Sun. */
export function sunEci(doy: number): Vec3 {
  const th = sunRa(doy);
  const dec = OBLIQUITY * Math.sin(th);
  return [Math.cos(dec) * Math.cos(th), Math.cos(dec) * Math.sin(th), Math.sin(dec)];
}

/** Greenwich angle [rad] for `t` seconds after 00:00 UTC of day `doy`. */
export function gmst(doy: number, t: number): number {
  return sunRa(doy) + Math.PI + (2 * Math.PI * t) / 86400;
}

/** ECI position [m]. */
export function positionEci(s: ScenarioSatellite, t: number): Vec3 {
  const r = RE_M + s.alt_m;
  const raan = (s.raan0_deg + s.raan_rate_deg_s * t) * DEG;
  const u = (s.u0_deg + s.n_deg_s * t) * DEG;
  const inc = s.inc_deg * DEG;
  const xo = r * Math.cos(u);
  const yo = r * Math.sin(u);
  const y1 = yo * Math.cos(inc);
  return [xo * Math.cos(raan) - y1 * Math.sin(raan), xo * Math.sin(raan) + y1 * Math.cos(raan), yo * Math.sin(inc)];
}

/** Rotates an ECI vector into the Earth-fixed frame. */
export function eciToEcef(p: Vec3, doy: number, t: number): Vec3 {
  const th = gmst(doy, t);
  const c = Math.cos(th);
  const s = Math.sin(th);
  return [p[0] * c + p[1] * s, -p[0] * s + p[1] * c, p[2]];
}

/** Earth-fixed position [m] of a geodetic point on orbitsim's sphere. */
export function siteEcef(latDeg: number, lonDeg: number, alt = 0): Vec3 {
  const r = RE_M + alt;
  const la = latDeg * DEG;
  const lo = lonDeg * DEG;
  return [r * Math.cos(la) * Math.cos(lo), r * Math.cos(la) * Math.sin(lo), r * Math.sin(la)];
}

/** Cylindrical umbra: behind the Earth and within RE of the Sun axis. */
export function isLit(p: Vec3, sun: Vec3): boolean {
  const d = p[0] * sun[0] + p[1] * sun[1] + p[2] * sun[2];
  if (d >= 0) {
    return true;
  }
  const x = p[0] - d * sun[0];
  const y = p[1] - d * sun[1];
  const z = p[2] - d * sun[2];
  return x * x + y * y + z * z >= RE_M * RE_M;
}

/** Range [m] and whether the segment stays above `RE + grazing`. */
export function lineOfSight(a: Vec3, b: Vec3, grazing: number): { range: number; clear: boolean } {
  const d: Vec3 = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const l2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
  const s = Math.min(1, Math.max(0, -(a[0] * d[0] + a[1] * d[1] + a[2] * d[2]) / Math.max(l2, 1)));
  const c: Vec3 = [a[0] + s * d[0], a[1] + s * d[1], a[2] + s * d[2]];
  const rr = RE_M + grazing;
  return { range: Math.sqrt(l2), clear: c[0] * c[0] + c[1] * c[1] + c[2] * c[2] > rr * rr };
}

/** Every satellite's state at one instant. */
export interface Snapshot {
  eci: Vec3[];
  ecef: Vec3[];
  lit: boolean[];
}

export function snapshot(sc: Scenario, t: number): Snapshot {
  const sun = sunEci(sc.epoch_doy);
  const eci = sc.satellites.map((s) => positionEci(s, t));
  return {
    eci,
    ecef: eci.map((p) => eciToEcef(p, sc.epoch_doy, t)),
    lit: eci.map((p) => isLit(p, sun)),
  };
}

/** A link to draw: satellite indices and its kind. */
export interface Link {
  i: number;
  j: number;
  kind: string;
}

/** Static links resolved to indices; a name the scenario lacks is skipped. */
export function staticLinks(sc: Scenario): Link[] {
  const idx = new Map(sc.satellites.map((s, i) => [s.name, i]));
  const out: Link[] = [];
  for (const [a, b, kind] of sc.links.static) {
    const i = idx.get(a);
    const j = idx.get(b);
    if (i !== undefined && j !== undefined) {
      out.push({ i, j, kind });
    }
  }
  return out;
}

/** Dynamic links at one instant, by the scenario's rules. */
export function dynamicLinks(sc: Scenario, snap: Snapshot): Link[] {
  const out: Link[] = [];
  const sats = sc.satellites;
  for (const rule of sc.links.dynamic) {
    const as = sats.map((s, i) => [s, i] as const).filter(([s]) => s.group === rule.a);
    const bs = sats.map((s, i) => [s, i] as const).filter(([s]) => s.group === rule.b);
    const seen = new Set<string>();
    for (const [sa, i] of as) {
      let best: { j: number; range: number } | undefined;
      for (const [sb, j] of bs) {
        if (i === j || (rule.different_cluster && sa.cluster === sb.cluster) || (rule.require_lit_b && !snap.lit[j])) {
          continue;
        }
        const { range, clear } = lineOfSight(snap.eci[i]!, snap.eci[j]!, rule.grazing_m);
        if (!clear || range > rule.max_range_m) {
          continue;
        }
        if (rule.nearest_only) {
          if (!best || range < best.range) {
            best = { j, range };
          }
          continue;
        }
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (!seen.has(key)) {
          seen.add(key);
          out.push({ i, j, kind: rule.kind });
        }
      }
      if (best) {
        out.push({ i, j: best.j, kind: rule.kind });
      }
    }
  }
  return out;
}

/** One orbit of a satellite, Earth-fixed for the epoch instant `t`, as a closed ring of points. */
export function orbitRing(s: ScenarioSatellite, doy: number, t: number, steps = 120): Vec3[] {
  return orbitRingEci(s, t, steps).map((p) => eciToEcef(p, doy, t));
}

/** The same ring in ECI, frozen at `t`. */
function orbitRingEci(s: ScenarioSatellite, t: number, steps: number): Vec3[] {
  const period = 360 / s.n_deg_s;
  const frozen = { ...s, raan_rate_deg_s: 0, raan0_deg: s.raan0_deg + s.raan_rate_deg_s * t };
  const out: Vec3[] = [];
  for (let k = 0; k <= steps; k++) {
    out.push(positionEci(frozen, t + (period * k) / steps));
  }
  return out;
}

/** The ring's umbra arc, Earth-fixed at `t`; empty when the plane never enters the umbra. */
export function shadowArc(s: ScenarioSatellite, doy: number, t: number, steps = 240): Vec3[] {
  const sun = sunEci(doy);
  const ring = orbitRingEci(s, t, steps).slice(0, steps);
  const lit = ring.map((p) => isLit(p, sun));
  const start = lit.findIndex((v, k) => !v && lit[(k - 1 + steps) % steps]);
  if (start < 0) {
    return [];
  }
  const out: Vec3[] = [];
  for (let k = 0; k < steps && !lit[(start + k) % steps]; k++) {
    out.push(eciToEcef(ring[(start + k) % steps]!, doy, t));
  }
  return out;
}

/** What an orbit plane looks like from the Sun at `t`. */
export interface PlaneGeometry {
  /** Earth-fixed ascending node on the orbit [m]. */
  node: Vec3;
  /** The descending node, opposite the ascending one: local time LTAN ± 12 h. */
  descNode: Vec3;
  /** Local mean solar time of the ascending node [h], 0 to 24: what LTAN means. */
  ltanH: number;
  /** Angle between the Sun direction and the orbit plane [deg]. */
  betaDeg: number;
}

export function planeGeometry(s: ScenarioSatellite, doy: number, t: number): PlaneGeometry {
  const raan = (s.raan0_deg + s.raan_rate_deg_s * t) * DEG;
  const inc = s.inc_deg * DEG;
  const r = RE_M + s.alt_m;
  const sun = sunEci(doy);
  const w: Vec3 = [Math.sin(raan) * Math.sin(inc), -Math.cos(raan) * Math.sin(inc), Math.cos(inc)];
  const beta = Math.asin(sun[0] * w[0] + sun[1] * w[1] + sun[2] * w[2]) / DEG;
  const ltan = (((12 + (raan - sunRa(doy)) / DEG / 15) % 24) + 24) % 24;
  const node = eciToEcef([r * Math.cos(raan), r * Math.sin(raan), 0], doy, t);
  return { node, descNode: [-node[0], -node[1], -node[2]], ltanH: ltan, betaDeg: beta };
}

/** The equator point, `alt` above the sphere, whose local mean solar time is `hour`. */
export function equatorAtLocalTime(doy: number, t: number, hour: number, alt = 0): Vec3 {
  return siteEcef(0, subsolarLonDeg(doy, t) + (hour - 12) * 15, alt);
}

/** The equator as a closed ring, `alt` above the sphere. */
export function equatorRing(alt = 0, steps = 180): Vec3[] {
  const out: Vec3[] = [];
  for (let k = 0; k <= steps; k++) {
    out.push(siteEcef(0, (360 * k) / steps, alt));
  }
  return out;
}

/** Longitude [deg] where the Sun is overhead at `t`: local time 12:00 there. */
export function subsolarLonDeg(doy: number, t: number): number {
  const p = eciToEcef(sunEci(doy), doy, t);
  return Math.atan2(p[1], p[0]) / DEG;
}

/** The meridian whose local mean solar time is `hour`, pole to pole, `alt` above the sphere. */
export function localTimeMeridian(doy: number, t: number, hour: number, alt = 15e3, steps = 60): Vec3[] {
  const lon = subsolarLonDeg(doy, t) + (hour - 12) * 15;
  const out: Vec3[] = [];
  for (let k = 0; k <= steps; k++) {
    out.push(siteEcef(-88 + (176 * k) / steps, lon, alt));
  }
  return out;
}

/** The day-night boundary: the great circle facing the Sun edge-on, Earth-fixed at `t`. */
export function terminator(doy: number, t: number, alt = 20e3, steps = 180): Vec3[] {
  const s = sunEci(doy);
  // Two unit vectors orthogonal to the Sun span the terminator plane.
  const a: Vec3 = Math.abs(s[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
  const e1 = normalize(cross(s, a));
  const e2 = cross(s, e1);
  const r = RE_M + alt;
  const out: Vec3[] = [];
  for (let k = 0; k <= steps; k++) {
    const th = (2 * Math.PI * k) / steps;
    out.push(
      eciToEcef([r * (e1[0] * Math.cos(th) + e2[0] * Math.sin(th)), r * (e1[1] * Math.cos(th) + e2[1] * Math.sin(th)), r * (e1[2] * Math.cos(th) + e2[2] * Math.sin(th))], doy, t),
    );
  }
  return out;
}

/** Earth-fixed unit vector toward the Sun at `t`. */
export function sunEcef(doy: number, t: number): Vec3 {
  return eciToEcef(sunEci(doy), doy, t);
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

function normalize(a: Vec3): Vec3 {
  const n = Math.hypot(a[0], a[1], a[2]);
  return [a[0] / n, a[1] / n, a[2] / n];
}

/** "10:30" for 10.5. */
export function formatHour(h: number): string {
  const m = Math.round(h * 60) % (24 * 60);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}
