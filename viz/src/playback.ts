// Pure helpers for the co-simulation playback (no Cesium): event windows, link state, colours.
// Kept apart from play.ts so vitest can check them against a playback file.

export type PlayEvent = [number, string, Record<string, unknown>];

export interface PlayFrame {
  t: number;
  load: number[];
  kv: number[];
  e: [number, number][];
}

export interface PlayRun {
  summary: Record<string, number>;
  frames: PlayFrame[];
  events: PlayEvent[];
  good_curve: [number, number][];
  requests?: unknown[][];
}

export interface TraceEdge {
  u: number;
  v: number;
  kind: string;
  up: [number, number][];
}

export interface Playback {
  schema: string;
  name: string;
  title: string;
  description: string;
  delivery: string;
  frame_s: number;
  link_gbps: Record<string, number>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  scenario: any;
  trace: { nodes: { id: number; name: string; role: string }[]; edges: TraceEdge[]; dark: [number, number][][]; horizon_s: number };
  policies: string[];
  mean: Record<string, Record<string, number | null>>;
  runs: Record<string, PlayRun>;
}

/** How long (simulated seconds) an event stays drawn, so second-long transfers are visible at 60×. */
export const SHOW_S: Record<string, number> = {
  upload: 12,
  deliver: 12,
  mig: 60,
  mig_done: 0,
  mig_abort: 45,
  cut: 45,
  lost: 90,
};
export const MAX_SHOW_S = Math.max(...Object.values(SHOW_S));

/** Index of the first event at or after t (events are time-sorted). */
export function lowerBound(events: PlayEvent[], t: number): number {
  let lo = 0;
  let hi = events.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (events[mid]![0] < t) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo;
}

/** Events drawn at time t, newest first, at most `cap`. */
export function activeEvents(events: PlayEvent[], t: number, cap = 120): PlayEvent[] {
  const out: PlayEvent[] = [];
  for (let k = lowerBound(events, t + 1e-9) - 1; k >= 0; k--) {
    const ev = events[k]!;
    if (t - ev[0] > MAX_SHOW_S) {
      break;
    }
    const show = SHOW_S[ev[1]] ?? 0;
    if (show > 0 && t - ev[0] <= show) {
      out.push(ev);
      if (out.length >= cap) {
        break;
      }
    }
  }
  return out;
}

/** Whether a contact interval list contains t. */
export function isUp(up: [number, number][], t: number): boolean {
  let lo = 0;
  let hi = up.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const [a, b] = up[mid]!;
    if (t < a) {
      hi = mid - 1;
    } else if (t >= b) {
      lo = mid + 1;
    } else {
      return true;
    }
  }
  return false;
}

export function frameAt(run: PlayRun, frameS: number, t: number): PlayFrame | undefined {
  if (!run.frames.length) {
    return undefined;
  }
  const k = Math.min(run.frames.length - 1, Math.max(0, Math.floor(t / frameS + 1e-6)));
  return run.frames[k];
}

/** Heat colour for a fill fraction 0..1: teal -> green -> amber -> red, as CSS rgb(). */
export function heat(x: number): [number, number, number] {
  const stops: [number, [number, number, number]][] = [
    [0, [45, 212, 191]],
    [0.4, [74, 222, 128]],
    [0.7, [250, 204, 21]],
    [1, [239, 68, 68]],
  ];
  const v = Math.min(1, Math.max(0, x));
  for (let k = 1; k < stops.length; k++) {
    const [x1, c1] = stops[k]!;
    const [x0, c0] = stops[k - 1]!;
    if (v <= x1) {
      const f = (v - x0) / (x1 - x0);
      return [0, 1, 2].map((i) => Math.round(c0[i]! + (c1[i]! - c0[i]!) * f)) as [number, number, number];
    }
  }
  return stops[stops.length - 1]![1];
}

/** Value of a step curve [[t, v], ...] at t. */
export function curveAt(curve: [number, number][], t: number): number {
  let v = 0;
  for (const [tt, vv] of curve) {
    if (tt > t) {
      break;
    }
    v = vv;
  }
  return v;
}

export const POLICY_NAMES: Record<string, string> = {
  greedy: "贪心放置 (不迁移)",
  reactive: "反应式迁移 (进影就搬)",
  ephemeris: "星历放置 (不迁移)",
  contact_aware: "星历放置 + 接触感知迁移",
};

export const POLICY_COLORS: Record<string, string> = {
  greedy: "#94a3b8",
  reactive: "#f59e0b",
  ephemeris: "#60a5fa",
  contact_aware: "#34d399",
};
