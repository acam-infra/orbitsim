// Find good moments to watch in a playback: busiest migration minute per policy, and the minute
// where contact_aware has gained the most over greedy.  node scripts/find_moments.mjs <playback.json>
import { readFileSync } from "node:fs";

const pb = JSON.parse(readFileSync(process.argv[2], "utf8"));
const names = pb.trace.nodes.map((n) => n.name);
for (const [pol, run] of Object.entries(pb.runs)) {
  const per = new Map();
  for (const [t, k] of run.events) {
    if (k === "mig") per.set(Math.floor(t / 60), (per.get(Math.floor(t / 60)) ?? 0) + 1);
  }
  const top = [...per.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
  const kinds = {};
  for (const e of run.events) kinds[e[1]] = (kinds[e[1]] ?? 0) + 1;
  console.log(pol.padEnd(18), "good_long", run.summary.good_long, "/", run.summary.n_long,
    "| busiest mig minutes", top.map(([m, c]) => `${m}min:${c}`).join(" "), "|", JSON.stringify(kinds));
}
const g = pb.runs.greedy?.good_curve;
const c = pb.runs.contact_aware?.good_curve;
if (g && c) {
  let best = [0, 0];
  let prev = 0;
  let steep = [0, 0];
  c.forEach(([t, v], k) => {
    const d = v - g[k][1];
    if (d > best[1]) best = [t, d];
    if (d - prev > steep[1] && k % 10 === 0) steep = [t, d - prev];
    if (k % 10 === 0) prev = d;
  });
  console.log("contact_aware - greedy: max lead", best[1], "at t =", best[0], "s | steepest 5-min gain", steep[1], "ending", steep[0], "s");
}
// first migration in the busiest window of contact_aware, with names
const ca = pb.runs.contact_aware;
if (ca) {
  const migs = ca.events.filter((e) => e[1] === "mig").slice(0, 400);
  const sample = migs.filter((e) => e[0] > 1200).slice(0, 3);
  for (const [t, , d] of sample) {
    console.log(`t=${t} mig req ${d.req} ${names[d.src]} -> ${names[d.dst]} ${d.GB.toFixed(2)} GB ${d.path.length - 1} hops`);
  }
}
