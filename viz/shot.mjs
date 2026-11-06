// Screenshots the viewer, one scenario at a time: the page as it opens, then on `day` if given.
//   node shot.mjs [base-url] [out-dir] [scenario,scenario,...] [day]
// Uses Playwright's Chromium, or a local Chrome / Edge with SHOT_CHANNEL=chrome|msedge.
import { chromium } from "@playwright/test";

const base = process.argv[2] ?? "http://localhost:5288";
const out = process.argv[3] ?? ".";
const names = (process.argv[4] ?? "sow-sso2,sow-relay,synth-w53").split(",");
const day = process.argv[5];

const browser = await chromium.launch({
  channel: process.env.SHOT_CHANNEL,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("response", (r) => r.status() >= 400 && errors.push(`${r.status()} ${r.url()}`));
for (const n of names) {
  await page.goto(`${base}/?s=${n}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(6000);
  if (day !== undefined) {
    await page.$eval(
      "#day",
      (el, d) => {
        el.value = d;
        el.dispatchEvent(new Event("input"));
      },
      day,
    );
    await page.waitForTimeout(3000);
  }
  await page.screenshot({ path: `${out}/vis-${n}${day !== undefined ? `-d${day}` : ""}.png` });
  console.log(n, await page.textContent("#stats"), "|", await page.textContent("#dayLabel"));
}
console.log("errors:", errors.slice(0, 10));
await browser.close();
