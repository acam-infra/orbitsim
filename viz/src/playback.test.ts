import { describe, expect, it } from "vitest";

import {
  activeEvents,
  curveAt,
  heat,
  isUp,
  lowerBound,
  nextMigrationTime,
  type Playback,
  type PlayEvent,
  SHOW_S,
  takeawayFor,
} from "./playback";

const ev: PlayEvent[] = [
  [10, "upload", { path: [0, 3] }],
  [20, "mig", { src: 3, dst: 4, path: [3, 4] }],
  [25, "deliver", { path: [4, 0] }],
  [100, "cut", { tag: "mig" }],
  [150, "mig", { src: 4, dst: 5, path: [4, 5] }],
];

describe("playback helpers", () => {
  it("finds the first event at or after t", () => {
    expect(lowerBound(ev, 0)).toBe(0);
    expect(lowerBound(ev, 20)).toBe(1);
    expect(lowerBound(ev, 21)).toBe(2);
    expect(lowerBound(ev, 1000)).toBe(5);
  });

  it("keeps each event drawn for its kind's window, newest first", () => {
    expect(activeEvents(ev, 15).map((e) => e[1])).toEqual(["upload"]);
    expect(activeEvents(ev, 30).map((e) => e[1])).toEqual(["deliver", "mig"]);
    expect(activeEvents(ev, 20 + SHOW_S.mig! + 1).map((e) => e[1])).toEqual([]);
    expect(activeEvents(ev, 120).map((e) => e[1])).toEqual(["cut"]);
  });

  it("hides upload and deliver arrows when includeIo is false", () => {
    expect(activeEvents(ev, 15, 120, false)).toEqual([]);
    expect(activeEvents(ev, 30, 120, false).map((e) => e[1])).toEqual(["mig"]);
    expect(activeEvents(ev, 120, 120, false).map((e) => e[1])).toEqual(["cut"]);
  });

  it("finds the next migration strictly after t", () => {
    expect(nextMigrationTime(ev, 0)).toBe(20);
    expect(nextMigrationTime(ev, 20)).toBe(150);
    expect(nextMigrationTime(ev, 149.9)).toBe(150);
    expect(nextMigrationTime(ev, 150)).toBeUndefined();
  });

  it("summarizes scenario takeaway in one sentence", () => {
    const pbMesh = {
      description: "fallback",
      mean: {
        greedy: { good_long_frac: 0.959 },
        ephemeris: { good_long_frac: 0.993 },
        contact_aware: { good_long_frac: 0.999, lat_long_p90_s: 330 },
      },
    } as unknown as Playback;
    expect(takeawayFor(pbMesh)).toContain("95.9%");
    expect(takeawayFor(pbMesh)).toContain("99.3%");
    expect(takeawayFor(pbMesh)).toContain("99.9%");

    const pbDisconnected = {
      description: "fallback",
      mean: {
        greedy: { good_long_frac: 0.693, lat_long_p90_s: 1994 },
        ephemeris: { good_long_frac: 0.707 },
        contact_aware: { good_long_frac: 0.694, lat_long_p90_s: 1991 },
      },
    } as unknown as Playback;
    expect(takeawayFor(pbDisconnected)).toContain("拓扑");
  });

  it("reads contact intervals as half-open", () => {
    const up: [number, number][] = [
      [0, 10],
      [20, 30],
    ];
    expect(isUp(up, 0)).toBe(true);
    expect(isUp(up, 10)).toBe(false);
    expect(isUp(up, 25)).toBe(true);
    expect(isUp(up, 30)).toBe(false);
    expect(isUp([], 5)).toBe(false);
  });

  it("steps a cumulative curve", () => {
    const c: [number, number][] = [
      [0, 0],
      [30, 2],
      [60, 5],
    ];
    expect(curveAt(c, 45)).toBe(2);
    expect(curveAt(c, 60)).toBe(5);
  });

  it("maps fill to a heat colour from teal to red", () => {
    expect(heat(0)).toEqual([45, 212, 191]);
    expect(heat(1)).toEqual([239, 68, 68]);
    expect(heat(2)).toEqual([239, 68, 68]);
  });
});
