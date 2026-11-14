import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";

test.beforeEach(async ({ page }) => {
  // Local Uvicorn trusts only the loopback proxy. Give each test a distinct
  // documentation-range simulated peer; production Nginx overwrites this header.
  const suffix = randomUUID()
    .replaceAll("-", "")
    .slice(0, 24)
    .match(/.{4}/g)
    .join(":");
  await page.setExtraHTTPHeaders({ "X-Forwarded-For": `2001:db8:${suffix}` });
});

async function ready(page) {
  await expect(page.locator('#map canvas[data-rendered="true"]')).toBeVisible({
    timeout: 15000,
  });
  await expect(page.locator("#refresh-time")).toContainText("Read", {
    timeout: 15000,
  });
}

test("Cyber context counts follow the period and overlay visibility", async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.goto("/");
  await ready(page);
  await expect(page.locator("#refresh")).toBeEnabled();
  const response = page.waitForResponse(
    (res) => res.url().includes("/api/cyber/relations?") && res.ok(),
  );
  await page.locator("#period").selectOption("720");
  const network = await (await response).json();
  // The summary updates after the full map refresh, not at the first response.
  await expect(page.locator("#refresh")).toBeEnabled({ timeout: 90000 });
  await expect(page.locator("#network-summary")).toContainText(
    `Cyber: ${network.report_count} reports · ${network.edges.length} context links`,
  );
  await page.locator(".map-options-details > summary").click();
  await page.locator("#cyber-connections").uncheck();
  await expect(page.locator("#network-summary")).not.toContainText("Cyber:");
  await page.locator("#cyber-connections").check();
  await expect(page.locator("#network-summary")).toContainText(
    `Cyber: ${network.report_count} reports`,
  );
});

test("world map initializes and real source events expose provenance", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await ready(page);
  await expect(page.locator('#map canvas[data-rendered="true"]')).toBeVisible();
  await expect(page.locator("#refresh")).toBeEnabled();
  await expect(page.locator("#load-error")).toBeHidden();
  await page.locator("#period").selectOption("720");
  await expect(page.locator(".event-button:not(.orbital-card)").first()).toBeVisible();
  await page.locator(".event-button:not(.orbital-card)").first().click();
  await expect(page.locator("#event-detail")).toBeVisible();
  await expect(page.locator("#event-detail")).toContainText(
    "Supporting reports",
  );
  await expect(
    page.locator("#event-detail .source-reference a").first(),
  ).toHaveAttribute("href", /^https:\/\//);
  expect(errors).toEqual([]);
  await page.locator("#reset-view").click();
  await expect
    .poll(async () =>
      Number(
        await page.locator("#map canvas").getAttribute("data-observations"),
      ),
    )
    .toBeGreaterThan(0);
  await page.locator("#event-detail .detail-close").click();
  await page.screenshot({ path: "docs/dashboard-desktop.png", fullPage: true });
});

test("layer state persists and country/timeline filtering works", async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.goto("/");
  await ready(page);
  await expect(page.locator("#refresh")).toBeEnabled();
  await page.locator('[data-layer="military"]').check();
  await page.reload();
  await expect(page.locator('[data-layer="military"]')).toBeChecked();
  await ready(page);
  await expect(page.locator("#refresh")).toBeEnabled();
  const response = page.waitForResponse(
    (response) =>
      response.url().includes("/api/events?") &&
      response.url().includes("country=IN"),
  );
  await page.locator("#country").selectOption("IN");
  await response;
  await expect(page.locator("#map-title")).toHaveText("India");
  await expect(page.locator("#country-insight")).toContainText("India");
  const timeResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/events?") &&
      response.url().includes("time_basis=published"),
  );
  await page.locator("#time-basis").selectOption("published");
  await timeResponse;
  await page.locator("#playback").click();
  await expect(page.locator("#playback")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.locator("#playback").click();
  await page.locator("#playhead").fill("50");
  await expect(page.locator("#list-label")).toHaveText(
    "HISTORICAL OBSERVATIONS",
  );
});

test("safe empty state, theme, collapsible panels and settings keyboard", async ({
  page,
}) => {
  await page.goto("/");
  await ready(page);
  await expect(page.locator("#refresh")).toBeEnabled();
  await page
    .locator("#search")
    .fill("A deliberately nonexistent research phrase");
  await page.locator("#search-form").getByRole("button").click();
  await expect(page.locator("#event-list")).toContainText(
    "No matching observations",
  );
  await page.locator("#theme").click();
  await expect(page.locator("html")).toHaveClass("light");
  for (const panel of ["left", "right", "bottom"]) {
    await page.locator(`[data-panel="${panel}"]`).click();
    await expect(page.locator(`[data-panel="${panel}"]`)).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    await page.locator(`[data-panel="${panel}"]`).click();
  }
  await page.locator("#settings-open").click();
  await expect(page.locator("#settings-dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator("#settings-dialog")).not.toBeVisible();
  await expect(page.locator("#settings-open")).toBeFocused();
});

test("provider outage, AI access dependency, sentiment categories", async ({
  page,
}) => {
  await page.goto("/");
  await ready(page);
  await expect(page.locator("#refresh")).toBeEnabled();
  await page.locator("#analysis-tab").click();
  await page.locator("#ai-question").fill("Summarize the available records");
  await page.locator("#ai-submit").click();
  await expect(page.locator("#ai-error")).toContainText("access token");
  await page.locator("#sentiment-tab").click();
  await page.locator("#sentiment-kind").selectOption("public");
  // Count varies with live collection; assert the summary rendered with a score breakdown.
  await expect(page.locator("#sentiment-summary")).toContainText(
    "scored English feed texts",
  );
  await expect(page.locator("#sentiment-summary")).toContainText("positive");
  await page.route("**/api/events?**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Synthetic test outage" }),
    }),
  );
  await page.locator("#refresh").click();
  await expect(page.locator("#load-error")).toContainText(
    "Synthetic test outage",
  );
  await expect(page.locator('#map canvas[data-ready="true"]')).toBeVisible();
});

test("mobile layout fits the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await ready(page);
  await expect(page.locator("#country-ribbon-body")).toBeHidden();
  await page
    .getByRole("button", { name: "Expand country leaderboard" })
    .click();
  await expect(page.locator("#country-ribbon-body")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "docs/dashboard-mobile.png", fullPage: true });
});

test("country ribbon ranks samples, supports keyboard selection and preserves comparison", async ({
  page,
}) => {
  const fixture = {
    items: [
      {
        country: "IN",
        name: "India",
        mentions: 30,
        mention_sources: 3,
        layer_count: 2,
        supported_records: 1,
        intelligence_records: 12,
        categories: { military: 6, geopolitical: 6 },
        score: 0.3,
        samples: 8,
      },
      {
        country: "FR",
        name: "France",
        mentions: 20,
        mention_sources: 2,
        layer_count: 3,
        supported_records: 2,
        intelligence_records: 9,
        categories: { cyber: 3, economic: 3, geopolitical: 3 },
        score: -0.4,
        samples: 9,
      },
      {
        country: "US",
        name: "United States of America",
        mentions: 10,
        mention_sources: 1,
        layer_count: 1,
        supported_records: 0,
        intelligence_records: 20,
        categories: { cyber: 20 },
        score: -0.9,
        samples: 1,
      },
    ],
    sentiment: {
      kind: "news",
      platform: "all",
      geography: "mentions",
      truncated: false,
    },
    methodology: {
      mentions: "Distinct reports",
      sentiment: "Wording only",
      intelligence: "Layer breadth",
    },
  };
  await page.route("**/api/country-activity?**", (route) =>
    route.fulfill({ json: fixture }),
  );
  await page.goto("/");
  await ready(page);
  await page.locator('[data-country-rank="mentions"]').click();
  const rows = page.locator(".country-rank-row");
  await expect(rows.first()).toHaveAttribute("data-country-rank-code", "IN");
  await page.locator('[data-country-rank="sentiment"]').click();
  await expect(rows.first()).toHaveAttribute("data-country-rank-code", "FR");
  await expect(rows.last()).toContainText("thin");
  await page.locator("#country-tone-order").selectOption("positive");
  await expect(rows.first()).toHaveAttribute("data-country-rank-code", "IN");
  await page.locator('[data-country-rank="intelligence"]').click();
  await expect(rows.first()).toHaveAttribute("data-country-rank-code", "FR");
  await rows.first().press("Enter");
  await expect(page.locator("#map-title")).toHaveText("France");
  await expect(page.locator('[data-country-rank-code="FR"]')).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(rows).toHaveCount(3);
  await expect(page.locator("#refresh")).toBeEnabled();
  await page.locator("#country-ribbon-reset").click();
  await expect(page.locator("#map-title")).toHaveText("World view");
  await page
    .getByRole("button", { name: "Collapse country leaderboard" })
    .click();
  await expect(page.locator("#country-ribbon-body")).toBeHidden();
  await page.reload();
  await expect(page.locator("#country-ribbon-body")).toBeHidden();
});

test("map renders distinct layer symbols and cluster badges while retaining aircraft", async ({
  page,
}) => {
  const errors = [];
  await page.route("**/api/aviation/live?**", (route) =>
    route.fulfill({ json: { available: false, items: [] } }),
  );
  await page.route("**/aircraft-live.json", (route) =>
    route.fulfill({ json: { available: false, items: [] } }),
  );
  page.on("pageerror", (error) => errors.push(error.message));
  const now = new Date().toISOString();
  const records = [
    ["geopolitical", -100, 40],
    ["military", 85, 55],
    ["maritime", 10, -22],
    ["cyber", 15, 52],
    ["economic", 20, -20],
    ["environment", -55, -10],
    ["military", -20, 20],
    ["military", -20, 20],
    ["cyber", 75, -30],
    ["economic", 75, -30],
    ["aviation", -10, 25],
    ["aviation", 35, 45],
  ].map(([category, longitude, latitude], i) => ({
    event_id: String(i).padStart(32, "0"),
    category,
    longitude,
    latitude,
    title: `Synthetic ${category} marker ${i}`,
    source_id: "synthetic",
    source_url: "https://example.org/test",
    time_key: now,
    published_at: now,
    ingested_at: now,
    confidence: "Single-source",
    location_precision: i % 2 ? "regional" : "exact",
    tags: [],
    aircraft_category: i === 10 ? 4 : i === 11 ? 5 : null,
    aircraft_track_deg: i === 10 ? 90 : i === 11 ? 270 : null,
    aircraft_callsign: `TEST${i}`,
    aircraft: category === "aviation" ? { icao24: `abc${i}` } : null,
    vessel_course_deg: i === 2 ? 45 : null,
    vessel_speed_kn: i === 2 ? 10.5 : null,
    vessel_flag: i === 2 ? "GB" : null,
    vessel_type: i === 2 ? 79 : null,
  }));
  await page.route("**/api/events?**", (route) =>
    route.fulfill({
      json: { items: records, total: records.length, category_counts: {} },
    }),
  );
  await page.goto("/");
  await ready(page);
  const canvas = page.locator("#map canvas");
  await expect
    .poll(() => canvas.getAttribute("data-symbol-categories"))
    .toBe("cyber,economic,environment,geopolitical,military");
  await expect
    .poll(async () => Number(await canvas.getAttribute("data-cluster-symbols")))
    .toBeGreaterThanOrEqual(2);
  await expect
    .poll(async () => Number(await canvas.getAttribute("data-aircraft")))
    .toBe(2);
  await expect
    .poll(async () => Number(await canvas.getAttribute("data-vessels")))
    .toBe(1);
  // The maritime row reads the registered flag state and the last
  // self-reported AIS type beside the name.
  const vesselRow = page
    .locator("button.event-button")
    .filter({ hasText: "Synthetic maritime marker 2" });
  const facts = await vesselRow.locator(".vessel-card-facts").textContent();
  expect(facts, "flag state and vessel type should travel with the row").toContain(
    "United Kingdom",
  );
  expect(facts).toContain("79 · Cargo");
  await expect(
    vesselRow.locator("img[alt]"),
  ).toHaveAttribute("title", "United Kingdom flag");
  await expect(page.locator("#load-error")).toBeHidden();
  expect(errors).toEqual([]);
});

test("current aircraft cards show measured details without inventing an airport", async ({
  page,
}) => {
  const now = new Date().toISOString();
  const flight = {
    event_id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    category: "aviation",
    live: true,
    title: "Aircraft TEST123",
    source_id: "opensky",
    source_url: "https://opensky-network.org/network/explorer",
    time_key: now,
    published_at: now,
    ingested_at: now,
    occurred_at: now,
    longitude: 75,
    latitude: 20,
    aircraft_category: 4,
    aircraft_track_deg: 90,
    confidence: "Single-source",
    location_precision: "approximate",
    tags: ["ads-b", "abcdef"],
    aircraft: {
      registration_country: "Synthetic",
      barometric_altitude_m: 10000,
      speed_mps: 250,
      on_ground: false,
    },
    description: "Synthetic test fixture",
    report_count: 1,
    reports: [
      {
        title: "Aircraft TEST123",
        source_id: "opensky",
        source_url: "https://opensky-network.org/network/explorer",
        published_at: now,
      },
    ],
  };
  await page.route("**/api/aviation/live?**", (route) =>
    route.fulfill({
      json: {
        items: [flight],
        available: true,
        stale: false,
        collected_at: now,
        poll_seconds: 120,
      },
    }),
  );
  await page.goto("/");
  await ready(page);
  const card = page.locator(
    '.event-button[data-event-id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]',
  );
  await expect(card).toContainText("Registration country");
  await expect(card).toContainText("32,808 ft");
  await expect(card).toContainText("486 kt");
  await expect(page.locator('[data-count="aviation"]')).toHaveText("1");
  await card.click();
  await expect(page.locator("#event-detail")).toContainText(
    "registration country is not departure origin",
  );
  await expect(page.locator("#event-detail")).toContainText("Airborne");
  await expect(
    page.locator("#event-detail .source-reference a"),
  ).toHaveAttribute("href", "https://opensky-network.org/network/explorer");
  await expect(page.locator("#load-error")).toBeHidden();
});

test("plain AI drafts render as text with context sources instead of invented citations", async ({
  page,
}) => {
  await page.route("**/api/ai/analyze", (route) =>
    route.fulfill({
      json: {
        output_mode: "draft",
        draft_text: "Draft <img src=x onerror=alert(1)> assessment",
        claims: [],
        limitations: ["Citations could not be validated."],
        model: "synthetic",
        analyzed_at: new Date().toISOString(),
        references: [{ source_url: "https://example.org/report" }],
      },
    }),
  );
  await page.goto("/");
  await ready(page);
  await page.locator("#settings-open").click();
  await page.locator("#admin-token").fill("synthetic-test-token");
  await page.locator('#settings-form button[type="submit"]').click();
  await page.locator("#analysis-tab").click();
  await page.locator("#ai-question").fill("Summarize sources");
  await page.locator("#ai-submit").click();
  await expect(page.locator("#ai-result")).toContainText(
    "AI draft · citations not validated",
  );
  await expect(page.locator("#ai-result")).toContainText(
    "<img src=x onerror=alert(1)>",
  );
  await expect(page.locator("#ai-result img")).toHaveCount(0);
  await expect(page.locator("#ai-result")).toContainText(
    "Sources supplied for context",
  );
});

test("reported aircraft changes animate briefly and stop for reduced motion", async ({
  page,
}) => {
  let reads = 0;
  const now = new Date();
  await page.route("**/api/aviation/live?**", (route) => {
    reads++;
    const time = new Date(
      now.getTime() - (reads === 1 ? 120000 : 0),
    ).toISOString();
    return route.fulfill({
      json: {
        available: true,
        stale: false,
        collected_at: time,
        poll_seconds: 120,
        items: [
          {
            event_id: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            live: true,
            category: "aviation",
            title: "Aircraft TESTMOVE",
            source_id: "opensky",
            source_url: "https://example.org/test",
            longitude: reads === 1 ? 75 : 75.2,
            latitude: 20,
            time_key: time,
            published_at: time,
            ingested_at: time,
            aircraft_category: 4,
            aircraft_track_deg: reads === 1 ? 359 : 1,
            confidence: "Single-source",
            location_precision: "approximate",
            tags: ["ads-b", "abcdef"],
          },
        ],
      },
    });
  });
  await page.goto("/");
  await ready(page);
  await expect(
    page.locator(".event-button").filter({ hasText: "TESTMOVE" }),
  ).toBeVisible();
  await expect(page.locator("#refresh")).toBeEnabled();
  await page.locator("#refresh").click();
  await expect
    .poll(async () =>
      Number(
        await page.locator("#map canvas").getAttribute("data-aircraft-moving"),
      ),
    )
    .toBe(1);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("#map canvas")).toHaveAttribute(
    "data-aircraft-moving",
    "0",
  );
  await expect(page.locator("#load-error")).toBeHidden();
});
