import { test, expect } from "@playwright/test";

const moment = new Date(Date.now() - 3600000).toISOString();
const catalog = {
  layers: [{ id: "aircraft", label: "ADS-B aircraft", group: "Air & sea" }],
  sources: [],
  source_count: 0,
  healthy_source_count: 0,
  history: {
    first: null,
    observations: 0,
    retention_days: 7,
    max_rows: 250000,
  },
  capabilities: [
    {
      id: "watches",
      name: "Spatial and entity watch rules",
      sources: [],
      workflow: "watches",
    },
  ],
};
const observation = {
  id: "a".repeat(64),
  source_id: "fixture",
  entity_id: "fixture-aircraft",
  title: "Synthetic watch evidence",
  category: "aviation",
  layers: ["aircraft"],
  source_url: "https://example.org/observation",
  latitude: 0.5,
  longitude: 0.5,
  observed_at: moment,
  received_at: moment,
  location_precision: "approximate",
};

async function setup(page) {
  const calls = [];
  const watchRows = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname;
    const body = request.method() === "POST" ? request.postDataJSON() : null;
    calls.push({ path, body, authorization: request.headers().authorization });
    let data = {};
    if (path.endsWith("/catalog")) data = catalog;
    if (path.endsWith("/frame"))
      data = { items: [], gnss: { type: "FeatureCollection", features: [] } };
    if (path.endsWith("/orbits"))
      data = { snapshot: null, basis: "No retained elements" };
    if (path.endsWith("/watches")) {
      if (body) {
        watchRows.push({
          id: "b".repeat(32),
          name: body.name,
          enabled: 1,
          config: { ...body, cooldown_seconds: 600 },
        });
        data = { id: "b".repeat(32) };
      } else data = { items: watchRows };
    }
    if (path.endsWith("/evaluate")) data = { alerts_created: 1 };
    if (path.endsWith("/alerts"))
      data = {
        items: [
          {
            id: "c".repeat(64),
            name: "Fixture watch",
            triggered_at: moment,
            snapshot: { observation },
          },
        ],
      };
    if (path.endsWith("/assets/import")) data = { stored: 1 };
    if (path.endsWith("/assets"))
      data = {
        items: [
          {
            id: "d".repeat(64),
            name: "Fixture supplier",
            kind: "supplier",
            version: "v1",
            geometry: { type: "Point", coordinates: [0.5, 0.5] },
          },
        ],
      };
    if (path.endsWith("/scenes/search"))
      data = {
        items: [0, 1].map((i) => ({
          id: String(i + 1).repeat(64),
          native_id: `Synthetic water product ${i + 1}`,
          provider: "opera-water",
          acquired_at: new Date(Date.now() - (3 - i) * 86400000).toISOString(),
          assets: {},
          metadata: { source_url: "https://example.org/product" },
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [0, 0],
                [1, 0],
                [1, 1],
                [0, 1],
                [0, 0],
              ],
            ],
          },
        })),
      };
    if (path.endsWith("/scenes/compare"))
      data = {
        id: "e".repeat(32),
        kind: "water",
        new_water_hectares: 1,
        valid_pixels: 3,
        valid_coverage_fraction: 0.75,
        interpretation:
          "Change in classified surface water, not proof of flooding or damage",
      };
    if (path.endsWith("/evidence"))
      data = { id: "f".repeat(32), sha256: "0".repeat(64) };
    if (path.endsWith("/recon"))
      data = {
        kind: "wikidata",
        lookup_id: "9".repeat(32),
        candidates: [
          {
            id: "Q123",
            label: "Synthetic company candidate",
            match: "candidate; verification required",
            source_url: "https://www.wikidata.org/wiki/Q123",
            relations: [],
          },
        ],
        basis: "Knowledge-base candidate match",
      };
    if (path.endsWith("/enrichment/retain"))
      data = { relationship_ids: ["8".repeat(32)], status: "source_claim" };
    return route.fulfill({ json: data });
  });
  await page.goto("/monitoring.html");
  await page
    .getByRole("button", { name: "Investigations", exact: true })
    .click();
  return calls;
}

async function access(page) {
  await page.getByText("Operator access", { exact: true }).click();
  await page
    .getByLabel("Local administrator token")
    .fill("synthetic-local-token");
}

test("watches require operator access and expose retained alert evidence", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const calls = await setup(page);
  await page.getByText("Spatial and entity watches", { exact: true }).click();
  await page.getByLabel("Watch name", { exact: true }).fill("Fixture watch");
  await page
    .getByLabel("Exact entity ID (optional)", { exact: true })
    .fill("fixture-aircraft");
  await page.getByRole("button", { name: "Save watch", exact: true }).click();
  await expect(page.locator("#workflow-status")).toContainText(
    "Enter the local administrator token",
  );
  expect(calls.filter((r) => r.path.endsWith("/watches"))).toHaveLength(0);
  await page
    .getByLabel("Local administrator token")
    .fill("synthetic-local-token");
  await page.getByRole("button", { name: "Save watch", exact: true }).click();
  await expect(page.locator("#watch-list")).toContainText("Fixture watch");
  expect(
    calls.find((r) => r.body?.name === "Fixture watch").body.entity_id,
  ).toBe("fixture-aircraft");
  await page.getByRole("button", { name: "Evaluate now", exact: true }).click();
  await expect(page.locator("#workflow-status")).toContainText(
    "1 alerts created",
  );
  await page.getByText("Retained alerts", { exact: true }).click();
  await page.getByRole("button", { name: "Load alerts", exact: true }).click();
  await page
    .getByRole("button", { name: "Inspect evidence", exact: true })
    .click();
  await expect(page.locator("#inspector")).toContainText(
    "Synthetic watch evidence",
  );
  await expect(page.locator("#observations-panel")).toBeVisible();
  expect(errors).toEqual([]);
});

test("authorized GeoJSON imports retain source version and render reference geometry", async ({
  page,
}) => {
  const calls = await setup(page);
  await access(page);
  await page
    .getByText("Infrastructure and supplier references", { exact: true })
    .click();
  for (const [id, value] of [
    ["asset-source", "fixture_assets"],
    ["asset-name", "Fixture assets"],
    ["asset-version", "v1"],
    ["asset-license", "Authorized synthetic fixture"],
    ["asset-url", "https://example.org/assets"],
  ])
    await page.locator(`#${id}`).fill(value);
  const data = {
    type: "FeatureCollection",
    features: [
      {
        id: "asset1",
        properties: { name: "Fixture supplier" },
        geometry: { type: "Point", coordinates: [0.5, 0.5] },
      },
    ],
  };
  await page
    .locator("#asset-file")
    .setInputFiles({
      name: "fixture.geojson",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(data)),
    });
  await page
    .getByRole("button", { name: "Import reference features", exact: true })
    .click();
  await expect(page.locator("#workflow-status")).toContainText(
    "1 versioned reference features imported",
  );
  expect(
    calls.find((r) => r.path.endsWith("/assets/import")).body.version,
  ).toBe("v1");
  await page
    .getByRole("button", {
      name: "Show retained reference geometry",
      exact: true,
    })
    .click();
  await expect(page.locator("#asset-results")).toContainText(
    "Fixture supplier",
  );
  await expect(page.locator("#monitor-map")).toHaveAttribute(
    "data-ready",
    "true",
  );
});

test("imagery pairs produce labeled measurements and attach immutable case evidence", async ({
  page,
}) => {
  const calls = await setup(page);
  await access(page);
  await page.locator("#workflow-case").fill("a".repeat(32));
  await page.getByText("Imagery and measured change", { exact: true }).click();
  await page.locator("#imagery-provider").selectOption("opera-water");
  await page.locator("#imagery-bbox").fill("0,0,1,1");
  await page
    .getByRole("button", { name: "Search scenes", exact: true })
    .click();
  await expect(page.locator("#scene-list")).toContainText(
    "Synthetic water product 1",
  );
  await page.locator("input[name='scene-before']").first().check();
  await page.locator("input[name='scene-after']").last().check();
  await page
    .getByRole("button", { name: "Compare selected acquisitions", exact: true })
    .click();
  await expect(page.locator("#comparison-results")).toContainText(
    "new water hectares",
  );
  await expect(page.locator("#comparison-results")).toContainText(
    "not proof of flooding",
  );
  await page
    .locator("#comparison-results")
    .getByRole("button", { name: "Attach to case" })
    .click();
  await expect(page.locator("#workflow-status")).toContainText(
    "Immutable evidence snapshot attached",
  );
  expect(calls.find((r) => r.path.endsWith("/evidence")).body.kind).toBe(
    "analysis",
  );
});

test("candidate enrichment stays labeled and mobile tools fit the viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const calls = await setup(page);
  await access(page);
  await page
    .getByText("Passive lookups and entity enrichment", { exact: true })
    .click();
  await page.locator("#recon-kind").selectOption("wikidata");
  await page.locator("#recon-target").fill("Synthetic company");
  await page
    .getByRole("button", { name: "Read public records", exact: true })
    .click();
  await expect(page.locator("#recon-results")).toContainText(
    "verification required",
  );
  await page
    .getByRole("button", { name: "Retain candidate graph", exact: true })
    .click();
  await expect(page.locator("#workflow-status")).toContainText(
    "candidate remains unverified",
  );
  expect(
    calls.find((r) => r.path.endsWith("/enrichment/retain")).body.candidate_id,
  ).toBe("Q123");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...localStorage }).includes("synthetic-local-token"),
    ),
  ).toBe(false);
  await page.screenshot({
    path: "test-results/monitoring-workflows-mobile.png",
    fullPage: true,
  });
});
