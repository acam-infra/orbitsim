import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  betaOverYear,
  declinationDeg,
  dynamicLinks,
  eciToEcef,
  equatorAtLocalTime,
  formatHour,
  isLit,
  lineOfSight,
  onDay,
  localTimeMeridian,
  planeGeometry,
  positionEci,
  RE_M,
  type Scenario,
  shadowArc,
  snapshot,
  staticLinks,
  subsolarLonDeg,
  sunEci,
  sunEcef,
  umbraMinutes,
} from "./scenario";

const DIR = fileURLToPath(new URL("../public/scenarios/", import.meta.url));
const scenarios: Scenario[] = readdirSync(DIR)
  .filter((f) => f.endsWith(".json") && f !== "index.json")
  .map((f) => JSON.parse(readFileSync(DIR + f, "utf8")) as Scenario);

describe("orbitsim scenarios", () => {
  it("are exported", () => {
    expect(scenarios.length).toBeGreaterThan(0);
  });

  for (const sc of scenarios) {
    it(`${sc.name} matches the Python reference positions and lighting`, () => {
      const byName = new Map(sc.satellites.map((s) => [s.name, s]));
      const sun = sunEci(sc.epoch_doy);
      for (const c of sc.check) {
        const s = byName.get(c.sat)!;
        const eci = positionEci(s, c.t);
        const p = eciToEcef(eci, sc.epoch_doy, c.t);
        const err = Math.hypot(p[0] - c.ecef[0], p[1] - c.ecef[1], p[2] - c.ecef[2]);
        expect(err).toBeLessThan(1);
        expect(isLit(eci, sun)).toBe(c.lit);
      }
    });

    it(`${sc.name} resolves every static link`, () => {
      expect(staticLinks(sc)).toHaveLength(sc.links.static.length);
    });
  }

  it("links never pass through the Earth", () => {
    const sc = scenarios.find((s) => s.links.dynamic.length > 0)!;
    for (const t of [0, 1800, 3600]) {
      const snap = snapshot(sc, t);
      for (const l of dynamicLinks(sc, snap)) {
        expect(lineOfSight(snap.eci[l.i]!, snap.eci[l.j]!, 0).clear).toBe(true);
      }
    }
  });

  it("an antipodal pair has no line of sight", () => {
    const a: [number, number, number] = [RE_M + 550e3, 0, 0];
    expect(lineOfSight(a, [-a[0], 0, 0], 80e3).clear).toBe(false);
  });

  it("geometry recovers each SSO plane's LTAN", () => {
    for (const sc of scenarios) {
      for (const s of sc.satellites.filter((x) => x.ltan_h !== null)) {
        const { ltanH } = planeGeometry(s, sc.epoch_doy, 0);
        const d = Math.abs(((ltanH - s.ltan_h! + 36) % 24) - 12);
        expect(d).toBeLessThan(1e-6);
      }
    }
  });

  it("the umbra arc is the closed-form eclipse fraction", () => {
    const sc = scenarios.find((s) => s.name === "sow-sso2")!;
    const s = sc.satellites[0]!;
    const { betaDeg } = planeGeometry(s, sc.epoch_doy, 0);
    const r = RE_M + s.alt_m;
    const frac = Math.acos(Math.sqrt(r * r - RE_M * RE_M) / (r * Math.cos((betaDeg * Math.PI) / 180))) / Math.PI;
    expect(Math.abs(shadowArc(s, sc.epoch_doy, 0, 720).length / 720 - frac)).toBeLessThan(0.005);
  });

  it("noon is under the Sun", () => {
    const lon = (subsolarLonDeg(81, 0) * Math.PI) / 180;
    const p = localTimeMeridian(81, 0, 12)[30]!;
    expect(Math.abs(Math.atan2(p[1], p[0]) - lon)).toBeLessThan(1e-9);
    // At 00:00 UTC the Sun is over the date line.
    expect(Math.abs(Math.abs(subsolarLonDeg(81, 0)) - 180)).toBeLessThan(1e-6);
  });

  it("the ascending node sits on the equator at its LTAN tick", () => {
    for (const sc of scenarios) {
      for (const s of sc.satellites) {
        for (const t of [0, 3600, 7200]) {
          const g = planeGeometry(s, sc.epoch_doy, t);
          expect(Math.abs(g.node[2])).toBeLessThan(1e-6);
          const tick = equatorAtLocalTime(sc.epoch_doy, t, g.ltanH, s.alt_m);
          expect(Math.hypot(g.node[0] - tick[0], g.node[1] - tick[1], g.node[2] - tick[2])).toBeLessThan(1);
        }
      }
    }
  });

  it("the subsolar latitude is the declination", () => {
    for (const d of [0, 81, 172, 264, 355]) {
      const p = sunEcef(d, 0);
      expect(Math.abs((Math.asin(p[2]) * 180) / Math.PI - declinationDeg(d))).toBeLessThan(1e-9);
    }
    expect(declinationDeg(172)).toBeGreaterThan(23.4);
    expect(Math.abs(declinationDeg(81))).toBeLessThan(1e-9);
  });

  it("an SSO plane keeps its LTAN on any day; beta and umbra match orbit_sun", () => {
    const sc = scenarios.find((x) => x.name === "sow-sso2")!;
    const s = sc.satellites[0]!; // LTAN 10:30, 550 km
    // orbit_sun.beta_angle_rad / eclipse_minutes for LTAN 10.5 at 550 km.
    const ref: Record<number, [number, number]> = { 0: [-17.29, 35.0], 172: [-23.61, 34.42], 264: [-22.27, 34.56], 355: [-17.19, 35.01] };
    for (const [d, [beta, umbra]] of Object.entries(ref)) {
      const day = Number(d);
      const moved = onDay({ ...sc, satellites: [s] }, day).satellites[0]!;
      const g = planeGeometry(moved, day, 0);
      expect(Math.abs(((g.ltanH - 10.5 + 36) % 24) - 12)).toBeLessThan(0.01);
      expect(Math.abs(g.betaDeg - beta)).toBeLessThan(0.1);
      expect(Math.abs(umbraMinutes(s, g.betaDeg) - umbra)).toBeLessThan(0.1);
    }
    expect(betaOverYear(sc, s, [0, 172])).toHaveLength(2);
  });

  it("formats hours", () => {
    expect(formatHour(10.5)).toBe("10:30");
    expect(formatHour(23.999)).toBe("00:00");
  });
});
