import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

const layers = JSON.parse(readFileSync("src/monitoring-layers.json", "utf8"));
const camera = {
  id: "a".repeat(64),
  source_id: "fixture",
  entity_id: "camera1",
  title: "Synthetic camera for browser validation",
  category: "sensors",
  layers: ["cctv"],
  observed_at: new Date(Date.now() - 60000).toISOString(),
  received_at: new Date().toISOString(),
  latitude: 1.3,
  longitude: 103.8,
  location_precision: "approximate",
  source_url: "https://example.org/camera",
  sensor: { kind: "cctv", reference: true },
};

test.beforeEach(async ({ page }) => {
  // Isolate test traffic from the user's loopback browser rate-limit bucket.
  const peer = randomUUID()
    .replaceAll("-", "")
    .slice(0, 24)
    .match(/.{4}/g)
    .join(":");
  await page.setExtraHTTPHeaders({ "X-Forwarded-For": `2001:db8:${peer}` });
  await page.route("**/api/monitoring/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/catalog"))
      return route.fulfill({
        json: {
          layers,
          sources: [],
          capabilities: [],
          source_count: 0,
          healthy_source_count: 0,
        },
      });
    if (url.pathname.endsWith("/frame"))
      return route.fulfill({
        json: {
          items: url.searchParams.has("at") ? [] : [camera],
          gnss: { type: "FeatureCollection", features: [] },
        },
      });
    return route.fulfill({ json: { items: [] } });
  });
});

test("monitoring layers are searchable in the main Intelligence layers panel", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator("#layer-search").fill("camera");
  await expect(
    page.locator('#left-panel [data-monitoring-layer="cctv"]'),
  ).toBeVisible();
  await expect(page.locator("#layer-search-result")).toContainText(
    "1 related layer",
  );
  expect(await page.locator("[data-monitoring-layer]").count()).toBe(58);
});

test("selecting monitoring evidence draws on the main map and exposes the inspector", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.locator("#layer-search").fill("camera");
  await page.locator('[data-monitoring-layer="cctv"]').check();
  await expect(page).toHaveURL(/5173\/$/);
  await expect(page.locator("#monitoring-view")).toBeVisible();
  await expect(page.locator("#monitor-message")).toContainText(
    "1 retained records",
  );
  await expect(page.locator("#map canvas")).toHaveAttribute(
    "data-monitoring",
    "1",
  );
  await page
    .getByRole("button", { name: /Synthetic camera for browser validation/ })
    .click();
  await expect(page.locator("#inspector")).toContainText(camera.source_id);
  await expect(page.locator("#inspector a").first()).toHaveAttribute(
    "href",
    camera.source_url,
  );
  await page.locator('[data-monitoring-layer="cctv"]').uncheck();
  await expect(page.locator("#map canvas")).toHaveAttribute(
    "data-monitoring",
    "0",
  );
  expect(errors).toEqual([]);
});

test("main timeline requests monitoring history at the selected playhead", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator("#layer-search").fill("camera");
  await page.locator('[data-monitoring-layer="cctv"]').check();
  await expect(page.locator("#monitor-message")).toContainText(
    "1 retained records",
  );
  const history = page.waitForRequest(
    (r) =>
      r.url().includes("/api/monitoring/frame?") &&
      new URL(r.url()).searchParams.has("at"),
  );
  await page.locator("#playhead").evaluate((el) => {
    el.value = "50";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const request = await history;
  expect(
    Date.parse(new URL(request.url()).searchParams.get("at")),
  ).toBeLessThan(Date.now() - 3600000);
  await expect(page.locator("#monitor-message")).toContainText("Playback");
  await expect(page.locator("#map canvas")).toHaveAttribute(
    "data-monitoring",
    "0",
  );
});

test("catalog failures preserve searchable layers and an explicit retry", async ({
  page,
}) => {
  await page.route("**/api/monitoring/catalog", (route) =>
    route.fulfill({ status: 404, json: { detail: "Not Found" } }),
  );
  await page.goto("/");
  await page.locator("#layer-search").fill("camera");
  await expect(page.locator('[data-monitoring-layer="cctv"]')).toBeVisible();
  await page.locator("#monitoring-open").click();
  await expect(page.locator("#monitor-message")).toContainText(
    "Restart the API and collector",
  );
  await expect(
    page.getByRole("button", { name: "Refresh monitoring data" }),
  ).toBeVisible();
});

test("mobile investigation tools stay on the dashboard and fit its width", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.locator("#monitoring-open").click();
  await page.locator("#show-investigations").click();
  await page.locator("#watch-tools summary").click();
  await page.locator("#watch-name").fill("Synthetic entity watch");
  await page.locator("#watch-entity").fill("test-entity");
  await page.getByRole("button", { name: "Save watch", exact: true }).click();
  await expect(page.locator("#operator-access")).toHaveAttribute("open", "");
  await expect(page.locator("#workflow-status")).toContainText(
    "administrator token",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(page).toHaveURL(/5173\/$/);
  await page.screenshot({
    path: "test-results/dashboard-monitoring-mobile.png",
    fullPage: true,
  });
});

test("the legacy Monitor URL has layers during an outage and a clear return", async ({
  page,
}) => {
  await page.route("**/api/monitoring/catalog", (route) =>
    route.fulfill({ status: 404, json: { detail: "Not Found" } }),
  );
  await page.goto("/monitoring.html");
  await page.getByLabel("Find a layer").fill("camera");
  await expect(
    page.getByLabel("Public traffic cameras", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Back to intelligence dashboard", exact: true })
    .click();
  await expect(page).toHaveURL(/5173\/$/);
  await expect(page.locator("#monitoring-open")).toBeVisible();
});

test("a monitoring deep link also opens tools on an already loaded dashboard", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("#monitoring-open")).toBeVisible();
  await page.evaluate(() => {
    location.hash = "monitoring";
  });
  await expect(page.locator("#monitoring-view")).toBeVisible();
  await expect(page.locator("#monitoring-tab")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});
