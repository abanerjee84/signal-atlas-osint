import { test, expect } from "@playwright/test";

const now = Date.now();
const first = new Date(now - 3600000).toISOString();
const camera = {
  id: "camera-1",
  entity_id: "camera-1",
  category: "analysis",
  title: "Synthetic public camera fixture",
  description: "Directory metadata, not a verified working stream",
  layers: ["cctv"],
  source_id: "tfl_cameras",
  source_url: "https://example.org/camera.mp4",
  latitude: 51.5,
  longitude: -0.12,
  observed_at: first,
  received_at: first,
  location_precision: "approximate",
  stale: false,
  sensor: { kind: "cctv" },
};
const catalog = {
  layers: [
    { id: "aircraft", label: "ADS-B aircraft", group: "Air & sea" },
    { id: "cctv", label: "Public traffic cameras", group: "Sensors" },
    { id: "radio", label: "Public radio receivers", group: "Sensors" },
  ],
  source_count: 2,
  healthy_source_count: 1,
  sources: [
    {
      source_id: "tfl_cameras",
      name: "TfL test fixture",
      state: "ok",
      last_success: first,
      limitation: "Public directory",
    },
    {
      source_id: "opensky",
      name: "OpenSky test fixture",
      state: "access_required",
      access_requirement: "Provider credentials required",
    },
  ],
  limitation: "Registered does not mean healthy",
  history: {
    first,
    last: new Date(now).toISOString(),
    observations: 2,
    retention_days: 7,
    max_rows: 250000,
  },
};

async function mock(page, { empty = false, fail = false } = {}) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    let data = {};
    if (url.pathname.endsWith("/catalog"))
      data = empty
        ? {
            ...catalog,
            history: { ...catalog.history, first: null, observations: 0 },
          }
        : catalog;
    if (url.pathname.endsWith("/frame")) {
      if (fail)
        return route.fulfill({
          status: 503,
          json: { detail: "Synthetic provider unavailable" },
        });
      data = {
        items: empty ? [] : [camera],
        truncated: false,
        gnss: { type: "FeatureCollection", features: [] },
      };
    }
    if (url.pathname.endsWith("/orbits"))
      data = {
        snapshot: null,
        basis: "No orbital elements retained at this time",
      };
    if (url.pathname.endsWith("/shodan"))
      return route.fulfill({
        status: 401,
        json: { detail: "Administrator authorization required" },
      });
    return route.fulfill({ json: data });
  });
}

test("layers, details, UTC playback and source health work together", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await mock(page);
  await page.goto("/monitoring.html");
  await expect(
    page.getByRole("button", { name: "Synthetic public camera fixture" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Synthetic public camera fixture" })
    .click();
  await expect(
    page.getByRole("button", { name: "Play public camera" }),
  ).toBeVisible();
  await page.locator("#playback-time").fill(first.slice(0, 16));
  await page.getByRole("button", { name: "Load time", exact: true }).click();
  await expect(page.locator("#mode")).toHaveText("Playback · UTC");
  await page
    .getByRole("button", { name: "Synthetic public camera fixture" })
    .click();
  await expect(
    page.getByText("This is historical metadata.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Play public camera" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Live", exact: true }).click();
  await expect(page.locator("#mode")).toContainText("Live");
  await page.getByText("Source health", { exact: true }).click();
  await expect(
    page.getByText("Provider credentials required", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Find a layer").fill("camera");
  await expect(
    page.getByLabel("Public traffic cameras", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Public radio receivers", { exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Public traffic cameras", { exact: true }).uncheck();
  await expect(page.locator("#record-count")).toHaveText("0");
  await page.screenshot({
    path: "test-results/monitoring-desktop.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("empty history disables playback and a narrow viewport does not overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mock(page, { empty: true });
  await page.goto("/monitoring.html");
  await expect(
    page.getByRole("button", { name: "Play history" }),
  ).toBeDisabled();
  await expect(page.locator("#history-note")).toContainText("No history yet");
  await expect(page.locator("#monitor-message")).toContainText(
    "No retained observations",
  );
  await expect(page.locator("#monitor-map")).toHaveAttribute(
    "data-ready",
    "true",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/monitoring-mobile.png",
    fullPage: true,
  });
});

test("failed frames expose a retry and protected lookups surface authorization errors", async ({
  page,
}) => {
  await mock(page, { fail: true });
  await page.goto("/monitoring.html");
  await expect(page.locator("#monitor-message")).toContainText(
    "Use Refresh to retry",
  );
  await page.getByText("Passive host lookup", { exact: true }).click();
  await page.getByLabel("Public IP address").fill("8.8.8.8");
  await page.getByRole("button", { name: "Look up host" }).click();
  await expect(page.locator("#lookup-result")).toHaveText(
    "Administrator authorization required",
  );
});
