// Screenshot the preview's pages in both themes, and optionally a hovered help tip.
//   node scripts/shot.mjs <page.html> <out-prefix> [--width 1400] [--views targets,runs,compare,tests]
//                         [--themes dark,light] [--hover "<view>|<css selector>"]
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);
const [page, out] = args;
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : fallback;
};
if (!page || !out) {
  console.error("usage: node scripts/shot.mjs <page.html> <out-prefix> [--width N] [--views a,b] [--themes dark,light] [--hover 'view|selector']");
  process.exit(2);
}
const width = Number(opt("width", "1400"));
const views = opt("views", "targets").split(",");
const themes = opt("themes", "dark,light").split(",");
const hover = opt("hover", "");

const browser = await chromium.launch();
try {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
  const tab = await ctx.newPage();
  // A file is the static preview (views are #hashes); an http URL is the running app (views are paths).
  const live = page.startsWith("http");
  const base = live ? page.replace(/\/$/, "") : pathToFileURL(page).href;
  const open = async (view) => {
    if (live) await tab.goto(`${base}${view.startsWith("/") ? view : "/" + view}`, { waitUntil: "networkidle" });
    else await tab.evaluate((v) => { location.hash = v; }, view);
    await tab.waitForTimeout(live ? 400 : 150);
  };
  if (!live) await tab.goto(base, { waitUntil: "load" });
  await tab.waitForTimeout(800); // web fonts
  for (const view of views) {
    await open(view);
    for (const theme of themes) {
      await tab.evaluate((t) => { document.documentElement.dataset.theme = t; }, theme);
      const file = `${out}-${view.replace(/\W+/g, "_")}-${theme}.png`;
      await tab.screenshot({ path: file, fullPage: true });
      console.log(file);
    }
  }
  if (hover) {
    const [view, selector] = hover.split("|");
    await open(view);
    await tab.evaluate(() => (document.documentElement.dataset.theme = "dark"));
    const el = tab.locator(selector).first();
    await el.scrollIntoViewIfNeeded();
    await el.hover();
    await tab.waitForTimeout(300);
    const box = await el.boundingBox();
    const clip = { x: Math.max(0, box.x - 380), y: Math.max(0, box.y - 60), width: 760, height: 420 };
    const file = `${out}-hover.png`;
    await tab.screenshot({ path: file, clip });
    console.log(file);
  }
} finally {
  await browser.close();
}
