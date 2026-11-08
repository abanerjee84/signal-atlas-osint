// Capture the running application with real retained data. No mocked requests,
// synthetic records, private case access, or provider credentials are used.
import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";

const baseURL = process.env.CAPTURE_BASE_URL || "http://127.0.0.1:5173";
const output = resolve("docs/screenshots");
const browser = await chromium.launch({
  headless: true,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 1,
});
const peer = randomUUID()
  .replaceAll("-", "")
  .slice(0, 24)
  .match(/.{4}/g)
  .join(":");
await context.setExtraHTTPHeaders({ "X-Forwarded-For": `2001:db8:${peer}` });
await context.addInitScript(() => {
  sessionStorage.setItem("osint.layers", JSON.stringify(["geopolitical"]));
  sessionStorage.setItem("osint.dashboard.monitoring", JSON.stringify([]));
});
const page = await context.newPage();
const errors = [];
const frameResponses = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("response", (response) => {
  if (new URL(response.url()).pathname === "/api/monitoring/frame")
    frameResponses.push(response.status());
});
const captures = [];

async function capture(file, subject, locator = page) {
  await page
    .locator("#map-progress")
    .waitFor({ state: "hidden", timeout: 180000 });
  await page.waitForTimeout(1000);
  // The documentation must never publish an operator token or private case ID.
  if (
    (await page.locator("#operator-token").inputValue()) ||
    (await page.locator("#workflow-case").inputValue())
  )
    throw new Error(
      "Private operator fields are populated; screenshot refused",
    );
  captures.push({
    file,
    subject,
    bytes: await locator.screenshot({ animations: "disabled" }),
  });
  console.log(`Captured ${file}`);
}

try {
  await page.goto(baseURL, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => document.querySelector("#map canvas")?.dataset.ready === "true",
    {},
    { timeout: 180000 },
  );
  await page.waitForFunction(
    () => document.querySelector("#refresh-time")?.textContent.includes("Read"),
    {},
    { timeout: 180000 },
  );
  const catalogResponse = await context.request.get(
    `${baseURL}/api/monitoring/catalog`,
  );
  if (!catalogResponse.ok())
    throw new Error(
      "The running monitoring API is unavailable; restart API and collector",
    );
  const catalog = await catalogResponse.json();
  if (!(await page.locator(".event-button").count()))
    throw new Error(
      "No collected public reports are available for the overview",
    );
  await page.locator("#reset-view").click();
  await page.waitForTimeout(1500);
  await capture(
    "dashboard-current.png",
    "Main dashboard with the unified eight-topic Map layers picker",
  );
  await capture(
    "map-layers-current.png",
    "The current topic-based layer picker",
    page.locator("#left-panel"),
  );

  await page.locator("#layer-search").fill("camera");
  await page.locator('[data-monitoring-layer="cctv"]').check();
  await page.waitForFunction(
    () => Number(document.querySelector("#map canvas")?.dataset.monitoring) > 0,
    {},
    { timeout: 180000 },
  );
  const singapore = page
    .locator(".dashboard-observation-row")
    .filter({ hasText: "Singapore traffic camera" });
  const record = (await singapore.count())
    ? singapore.first()
    : page.locator(".dashboard-observation-row").first();
  const recordTitle = await record.locator("strong").textContent();
  await record.click();
  await page.waitForFunction(
    () => Number(document.querySelector("#map canvas")?.dataset.monitoring) > 0,
  );
  await page.waitForTimeout(2000);
  await capture(
    "camera-record-current.png",
    "Real retained public camera record, location, timestamps and source attribution",
  );

  await page.locator("#monitoring-open").click();
  await page.locator("#watch-tools > summary").click();
  await page.locator("#layer-search").fill("");
  await page.locator("#reset-view").click();
  await page.locator("#right-content").evaluate((node) => (node.scrollTop = 0));
  await page.waitForTimeout(1800);
  await capture(
    "tools-current.png",
    "The Tools panel with spatial/entity watch setup and the main map",
  );
  if (errors.length)
    throw new Error(`Application errors during capture: ${errors.join("; ")}`);
  await mkdir(output, { recursive: true });
  for (const { file, bytes } of captures)
    await writeFile(resolve(output, file), bytes);
  const manifest = {
    captured_at: new Date().toISOString(),
    application_revision: execFileSync("git", ["rev-parse", "HEAD"], {
      encoding: "utf8",
    }).trim(),
    viewport: { width: 1920, height: 1080 },
    data: "Real retained public-source records from the running local application; no mocks or seeded records",
    source_definitions: catalog.source_count,
    healthy_sources_at_capture: catalog.healthy_source_count,
    observation_sublayers: catalog.layers.length,
    camera_record_title: recordTitle,
    screenshots: captures.map(({ file, subject }) => ({ file, subject })),
    privacy:
      "Fresh isolated browser context; operator token and private case fields verified empty; no private case APIs accessed",
  };
  await writeFile(
    resolve(output, "capture.json"),
    JSON.stringify(manifest, null, 2) + "\n",
  );
  console.log(
    JSON.stringify({
      screenshots: captures.map(({ file, bytes }) => ({
        file,
        bytes: bytes.length,
      })),
      source_definitions: catalog.source_count,
      observation_sublayers: catalog.layers.length,
    }),
  );
} catch (error) {
  console.error(
    JSON.stringify({
      error: error.message,
      layer_status: await page
        .locator("#monitor-message")
        .textContent()
        .catch(() => "unavailable"),
      frame_responses: frameResponses,
      application_errors: errors,
    }),
  );
  throw error;
} finally {
  await context.close();
  await browser.close();
}
