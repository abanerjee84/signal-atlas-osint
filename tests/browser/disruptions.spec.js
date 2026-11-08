import { openLayerTopic } from "./helpers/layers.js";
import { test, expect } from "@playwright/test";
import {
  DISRUPTION_BASIS,
  DISRUPTION_LIMITATION,
  disruptionFeatures,
  disruptionFields,
  measurementLabel,
} from "../../src/disruptions.js";
import { readFileSync } from "node:fs";

const PLACES = Object.fromEntries(
  JSON.parse(readFileSync("public/countries.geojson", "utf8")).features.map(
    (feature) => [feature.properties.code, feature.properties],
  ),
);

const ROW = {
  id: "a".repeat(32),
  source_id: "ioda",
  country: "MW",
  name: "Malawi",
  start_at: "2026-10-17T00:00:00+00:00",
  end_at: "2026-10-17T03:10:10+00:00",
  measurement_from: "2026-10-16T03:10:10+00:00",
  measurement_until: "2026-10-17T03:10:10+00:00",
  method: "median",
  datasource: "bgp",
  score: 2540.85,
  uncertainty: null,
  original_url: "https://example.org/ioda",
  retrieved_at: "2026-10-17T03:10:11+00:00",
};

test.describe("internet disruption records", () => {
  test("is placed at the country reference point, not a located incident", () => {
    const { features } = disruptionFeatures([ROW], PLACES);
    expect(features).toHaveLength(1);
    const properties = features[0].properties;
    expect(properties.location_precision).toBe("regional");
    expect(properties.basis).toBe(DISRUPTION_BASIS);
    expect(properties.basis).toContain("not at a located incident");
    expect(features[0].geometry.coordinates).toEqual(PLACES.MW.center);
  });

  test("reports an unplaceable country instead of guessing a neighbour", () => {
    const { features, unresolved } = disruptionFeatures(
      [{ ...ROW, country: "ZZ", name: "Nowhere" }],
      PLACES,
    );
    expect(features).toHaveLength(0);
    expect(unresolved).toEqual(["ZZ"]);
  });

  test("carries the provider's method, datasource and windows through", () => {
    const { features } = disruptionFeatures([ROW], PLACES);
    const properties = features[0].properties;
    expect(properties.method).toBe("median");
    expect(properties.datasource).toBe("bgp");
    expect(properties.measurement_from).toBe(ROW.measurement_from);
    expect(properties.measurement_until).toBe(ROW.measurement_until);
    expect(properties.original_url).toBe(ROW.original_url);
  });

  test("shows a missing uncertainty as absent rather than as a value", () => {
    const { features } = disruptionFeatures([ROW], PLACES);
    const fields = Object.fromEntries(disruptionFields(features[0].properties));
    expect(fields.Uncertainty).toBe("Not supplied by the provider");
    expect(fields["Aggregation"]).toBe("median");
    expect(fields["Datasource"]).toBe("bgp");
  });

  test("never calls a country aggregate a located outage", () => {
    const { features } = disruptionFeatures([ROW], PLACES);
    const fields = Object.fromEntries(disruptionFields(features[0].properties));
    expect(fields["Location precision"]).toContain("not a point incident");
    expect(DISRUPTION_LIMITATION).toContain("not a located outage");
  });

  test("sizes markers by rank within the response, never by raw cross-source score", () => {
    const rows = [
      { ...ROW, id: "1".repeat(32), score: 1 },
      { ...ROW, id: "2".repeat(32), score: 2 },
      { ...ROW, id: "3".repeat(32), score: 3 },
    ];
    const { features } = disruptionFeatures(rows, PLACES);
    const sizes = features.map((feature) => feature.properties.size);
    expect(Math.min(...sizes)).toBeGreaterThanOrEqual(0.25);
    expect(Math.max(...sizes)).toBeLessThanOrEqual(1);
    // Highest raw score gets the largest rank, independent of its magnitude.
    const highest = features.find((f) => f.properties.id === "3".repeat(32));
    expect(highest.properties.size).toBe(Math.max(...sizes));
  });

  test("renders the measurement window without collapsing it", () => {
    expect(
      measurementLabel({
        from: "2026-10-16T03:10:10+00:00",
        until: "2026-10-17T03:10:10+00:00",
      }),
    ).toContain("2026-10-16 03:10");
    expect(
      measurementLabel({
        from: "2026-10-16T03:10:10+00:00",
        until: "2026-10-17T03:10:10+00:00",
      }),
    ).toContain("2026-10-17 03:10");
    expect(measurementLabel(undefined)).toBe("measurement window not stated");
    expect(measurementLabel({})).toContain("?");
  });
});

test.describe("internet disruptions on the dashboard", () => {
  test("says a credential is needed rather than showing an empty map", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForSelector("#layers input[data-layer='disruptions']");
    await openLayerTopic(page, "cyber");
    await page.locator("#layers input[data-layer='disruptions']").check();
    await page.waitForTimeout(800);
    const row = page.locator("#layers .layer-row", {
      has: page.locator("[data-layer='disruptions']"),
    });
    await expect(row.locator(".layer-count")).toHaveText("—");
    await expect(row.locator(".layer-note")).toContainText("access token");
  });

  test("is hidden until switched on and draws nothing into event counts", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForFunction(
      () => document.querySelector("#map canvas")?.dataset.ready === "true",
      { timeout: 45000 },
    );
    await expect
      .poll(() => page.getAttribute("#map canvas", "data-disruptions-visible"))
      .toBe("false");
    expect(
      await page.getAttribute("#map canvas", "data-disruptions-loaded"),
    ).toBe("0");
    expect(
      await page.getAttribute("#map canvas", "data-disruptions-drawn"),
    ).toBe("0");
  });

  test("switching it on issues no dashboard record query", async ({ page }) => {
    // Stub every endpoint so the only requests that can happen are the ones this
    // test causes; background refresh timers otherwise make it timing dependent.
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.includes("/cyber/disruptions"))
        return route.fulfill({ json: { data: [], meta: {} } });
      if (path.endsWith("/events"))
        return route.fulfill({
          json: { items: [], total: 0, category_counts: {} },
        });
      if (path.includes("/timeline"))
        return route.fulfill({ json: { buckets: [], total: 0 } });
      return route.fulfill({ json: { data: [], meta: { total: 0 } } });
    });
    await page.goto("/");
    await page.waitForFunction(
      () => document.querySelector("#map canvas")?.dataset.ready === "true",
      { timeout: 45000 },
    );
    await page.waitForTimeout(2500);
    const queries = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname.startsWith("/api/"))
        queries.push(request.url());
    });
    await openLayerTopic(page, "cyber");
    await page.locator("#layers input[data-layer='disruptions']").check();
    await page.waitForTimeout(1500);
    // These records come from the evidence API, so enabling the layer must not
    // change which events the dashboard asks for.
    expect(
      queries.filter((url) => !url.includes("/api/v1/cyber/disruptions")),
    ).toEqual([]);
    // Without a credential the layer states that rather than calling out, so no
    // evidence request is expected here at all.
    const row = page.locator("#layers .layer-row", {
      has: page.locator("[data-layer='disruptions']"),
    });
    await expect(row.locator(".layer-count")).toHaveText("—");
    await expect(row.locator(".layer-note")).toContainText("access token");
  });

  test("states that it is a country aggregate in its own panel note", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForSelector("#layers input[data-layer='disruptions']");
    const row = page.locator("#layers .layer-row", {
      has: page.locator("[data-layer='disruptions']"),
    });
    await expect(row.locator(".layer-note")).toContainText(
      "not located incidents",
    );
  });
});
