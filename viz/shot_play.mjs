// Screenshots of the co-simulation playback at given simulated times, plus page errors.
//   node shot_play.mjs [base-url] [out-dir] [playback] [policy] [t1,t2,...]
import { chromium } from "@playwright/test";

const base = process.argv[2] ?? "http://localhost:5288";
const out = process.argv[3] ?? ".";
const name = process.argv[4] ?? "cosim_coop_w53_v1";
const policy = process.argv[5] ?? "contact_aware";
const times = (process.argv[6] ?? "1800").split(",").map(Number);

const browser = await chromium.launch({
  channel: process.env.SHOT_CHANNEL,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 950 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("response", (r) => r.status() >= 400 && errors.push(`${r.status()} ${r.url()}`));
for (const t of times) {
  await page.goto(`${base}/play.html?p=${name}&pol=${policy}&t=${t}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(7000);
  const file = `${out}/play-${name}-${policy}-t${t}.png`;
  await page.screenshot({ path: file });
  console.log(file, "|", (await page.textContent("#live"))?.replace(/\s+/g, " "));
}
console.log("errors:", errors.slice(0, 10));
await browser.close();
