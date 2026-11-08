import { openLayerTopic } from "./helpers/layers.js";
import { test, expect } from "@playwright/test";
import {
  nightStrips,
  terminatorLines,
  subsolarPoint,
  referenceData,
  REFERENCE_REGISTRY,
  referenceExplanation,
} from "../../src/reference-layers.js";

// Point-in-polygon for the strip quads, so the shaded area can be checked
// against where the sun actually is.
function inRing([x, y], ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi)
      inside = !inside;
  }
  return inside;
}

const isNight = (longitude, latitude, date) =>
  nightStrips(date).some((feature) =>
    inRing([longitude, latitude], feature.geometry.coordinates[0]),
  );

const wrap = (value) => ((((value + 180) % 360) + 360) % 360) - 180;

const DATES = [
  "2026-01-01T00:00:00Z",
  "2026-03-20T00:00:00Z",
  "2026-06-21T12:00:00Z",
  "2026-06-21T18:00:00Z",
  "2026-09-22T12:00:00Z",
  "2026-10-16T00:00:00Z",
  "2026-10-16T06:00:00Z",
  "2026-10-16T12:00:00Z",
  "2026-12-21T18:00:00Z",
];

// Sample away from the sun's own meridian, where the lit and night arcs meet and
// a point on the boundary has no defined side.
const LIT = [40, -40];
const DARK = [180 + 40, 180 - 40];

test.describe("solar position", () => {
  test("declination reaches the expected solstice and equinox values", () => {
    expect(
      subsolarPoint(new Date("2026-03-20T12:00:00Z")).latitude,
    ).toBeCloseTo(0, 0);
    expect(
      subsolarPoint(new Date("2026-06-21T12:00:00Z")).latitude,
    ).toBeCloseTo(23.4, 0);
    expect(
      subsolarPoint(new Date("2026-12-21T12:00:00Z")).latitude,
    ).toBeCloseTo(-23.4, 0);
  });

  test("declination stays within the obliquity all year", () => {
    for (let hour = 0; hour < 366 * 8; hour++) {
      const date = new Date(Date.UTC(2026, 0, 1) + hour * 3 * 3600e3);
      expect(Math.abs(subsolarPoint(date).latitude)).toBeLessThanOrEqual(23.5);
    }
  });

  test("subsolar longitude advances about 90 degrees per six hours", () => {
    const noon = subsolarPoint(new Date("2026-10-16T12:00:00Z")).longitude;
    const evening = subsolarPoint(new Date("2026-10-16T18:00:00Z")).longitude;
    expect(evening - noon).toBeCloseTo(-90, 0);
  });

  test("subsolar meridian sits near Greenwich at local noon", () => {
    expect(
      Math.abs(subsolarPoint(new Date("2026-03-20T12:00:00Z")).longitude),
    ).toBeLessThan(3);
  });
});

test.describe("terminator geometry", () => {
  test("the lit side is unshaded and the dark side is shaded all year", () => {
    for (let hour = 0; hour < 366 * 8; hour++) {
      const date = new Date(Date.UTC(2026, 0, 1) + hour * 3 * 3600e3);
      const sun = subsolarPoint(date);
      for (const offset of LIT)
        expect(
          isNight(wrap(sun.longitude + offset), sun.latitude, date),
          date.toISOString(),
        ).toBe(false);
      for (const offset of DARK)
        expect(
          isNight(wrap(sun.longitude + offset), -sun.latitude, date),
          date.toISOString(),
        ).toBe(true);
    }
  });

  test("polar daylight and polar night fall on the correct pole", () => {
    let checked = 0;
    for (let hour = 0; hour < 366 * 8; hour++) {
      const date = new Date(Date.UTC(2026, 0, 1) + hour * 3 * 3600e3);
      const sun = subsolarPoint(date);
      // Near the equinox both poles sit on the terminator and neither claim holds.
      if (Math.abs(sun.latitude) <= 5) continue;
      const darkPole = sun.latitude > 0 ? -89.5 : 89.5;
      for (const offset of [30, 90, 150]) {
        expect(
          isNight(wrap(sun.longitude + offset), darkPole, date),
          date.toISOString(),
        ).toBe(true);
        expect(
          isNight(wrap(sun.longitude + 180 + offset), -darkPole, date),
          date.toISOString(),
        ).toBe(false);
      }
      checked++;
    }
    expect(checked).toBeGreaterThan(2000);
  });

  test("every coordinate stays inside the map and the poles", () => {
    for (const iso of DATES) {
      const date = new Date(iso);
      const rings = nightStrips(date).map(
        (feature) => feature.geometry.coordinates[0],
      );
      for (const line of terminatorLines(date))
        rings.push(line.geometry.coordinates);
      for (const ring of rings)
        for (const [longitude, latitude] of ring) {
          expect(Number.isFinite(longitude), iso).toBe(true);
          expect(Number.isFinite(latitude), iso).toBe(true);
          expect(Math.abs(longitude), iso).toBeLessThanOrEqual(180.001);
          expect(Math.abs(latitude), iso).toBeLessThanOrEqual(90.001);
        }
    }
  });

  test("no polygon spans more than half the globe", () => {
    for (const iso of DATES)
      for (const feature of nightStrips(new Date(iso))) {
        const longitudes = feature.geometry.coordinates[0].map(
          (point) => point[0],
        );
        expect(
          Math.max(...longitudes) - Math.min(...longitudes),
          iso,
        ).toBeLessThanOrEqual(180.001);
      }
  });
});

test.describe("reference layer contract", () => {
  test("file layers declare a registry version, licence and retrieval date", () => {
    for (const entry of Object.values(REFERENCE_REGISTRY)) {
      if (entry.computed) continue;
      expect(entry.file, entry.id).toMatch(/^\/reference\/.+\.geojson$/);
      expect(entry.registry.version, entry.id).toBeTruthy();
      expect(entry.registry.license, entry.id).toBeTruthy();
      expect(entry.registry.retrieved, entry.id).toBeTruthy();
    }
  });

  test("every layer states its class, basis and limits", () => {
    for (const id of Object.keys(REFERENCE_REGISTRY)) {
      const fields = Object.fromEntries(referenceExplanation(id));
      expect(fields.Class, id).toContain("not an observation");
      expect(fields.Basis, id).toBeTruthy();
      expect(fields.Limits, id).toBeTruthy();
      expect(fields["Registry version"], id).toBeTruthy();
    }
  });

  test("computed geometry carries the registry version onto every feature", () => {
    const collection = referenceData(
      "terminator",
      new Date("2026-10-16T12:00:00Z"),
    );
    expect(collection.features.length).toBeGreaterThan(100);
    for (const feature of collection.features)
      expect(feature.properties.registry_version).toBe(
        REFERENCE_REGISTRY.terminator.registry.version,
      );
  });
});

test.describe("ports reference layer", () => {
  test("declares the registry version this build expects", async ({
    request,
  }) => {
    const response = await request.get("/reference/ports.geojson");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.metadata.registry_version).toBe(
      REFERENCE_REGISTRY.ports.registry.version,
    );
    expect(body.metadata.source_sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(body.metadata.license).toBe("Public domain");
  });

  test("carries published coordinates only", async ({ request }) => {
    const body = await (await request.get("/reference/ports.geojson")).json();
    expect(body.features.length).toBeGreaterThan(500);
    for (const feature of body.features.slice(0, 200)) {
      expect(feature.geometry.type).toBe("Point");
      const [longitude, latitude] = feature.geometry.coordinates;
      expect(Math.abs(longitude)).toBeLessThanOrEqual(180);
      expect(Math.abs(latitude)).toBeLessThanOrEqual(90);
      expect(feature.properties.name).toBeTruthy();
    }
  });

  test("does not trigger a record refetch or report a record total", async ({
    page,
  }) => {
    // Every dashboard endpoint is stubbed, so the only requests that can happen
    // are the ones this test causes. Without that, background refresh timers and
    // a rate-limited API make the assertion depend on timing.
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.includes("/cyber/disruptions"))
        return route.fulfill({ json: { data: [] } });
      if (path.endsWith("/events"))
        return route.fulfill({
          json: { items: [], total: 0, category_counts: {} },
        });
      if (path.includes("/timeline"))
        return route.fulfill({ json: { buckets: [], total: 0 } });
      return route.fulfill({ json: { data: [], meta: { total: 0 } } });
    });
    await page.goto("/");
    await openLayerTopic(page, "places");
    await page.waitForSelector("#layers input[data-layer='ports']");
    await page.waitForFunction(
      () => document.querySelector("#map canvas")?.dataset.ready === "true",
      { timeout: 45000 },
    );
    await page.waitForTimeout(2500);

    // Reference geometry is context. Switching it on must not ask the backend for
    // a different set of records.
    const queries = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname.startsWith("/api/"))
        queries.push(request.url());
    });
    await page.locator("#layers input[data-layer='ports']").check();
    await page.waitForTimeout(1500);
    expect(
      queries.filter((url) => !url.includes("/api/v1/cyber/disruptions")),
      "reference layers must not refetch records",
    ).toEqual([]);
    // And it reports its class rather than a number that reads as observations.
    expect(await page.textContent('[data-count="ports"]')).toBe("ref");
  });

  test("its explanation names the publisher, licence and limits", async ({
    page,
  }) => {
    await page.goto("/");
    await openLayerTopic(page, "places");
    await page.waitForSelector("#layers button[data-layer-info='ports']");
    await page.click("#layers button[data-layer-info='ports']");
    await page.waitForSelector("#reference-explanation");
    const fields = await page.$$eval("#reference-explanation dt", (labels) =>
      labels.map((label) => [
        label.textContent,
        label.nextElementSibling?.textContent,
      ]),
    );
    const lookup = Object.fromEntries(fields);
    expect(lookup.Class).toContain("not an observation");
    expect(lookup.Publisher).toBe("Natural Earth");
    expect(lookup.Licence).toBe("Public domain");
    expect(lookup["Registry version"]).toBeTruthy();
    expect(lookup["Load state"]).toContain("registry");
    expect(lookup["Load state"]).not.toContain("Unavailable");
  });
});

const OSM_LAYERS = [
  ["bases", "/reference/military-bases.geojson", 4000],
  ["nuclear", "/reference/nuclear-facilities.geojson", 150],
  ["spaceports", "/reference/spaceports.geojson", 20],
];

test.describe("OpenStreetMap reference layers", () => {
  for (const [id, file, minimum] of OSM_LAYERS) {
    test(`${id} declares the registry version this build expects`, async ({
      request,
    }) => {
      const response = await request.get(file);
      expect(response.status(), `${file} should be served`).toBe(200);
      const body = await response.json();
      expect(body.metadata.registry_version).toBe(
        REFERENCE_REGISTRY[id].registry.version,
      );
      expect(body.metadata.license).toBe("ODbL 1.0");
      expect(body.metadata.publisher).toBe("OpenStreetMap contributors");
      // The exact response has to be identifiable, not just the licence.
      expect(body.metadata.source_sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(body.metadata.source_query).toContain("out center");
      expect(body.features.length).toBeGreaterThanOrEqual(minimum);
    });

    test(`${id} carries attribution on every feature and no invented coordinates`, async ({
      request,
    }) => {
      const body = await (await request.get(file)).json();
      expect(body.features.length).toBeGreaterThan(0);
      for (const feature of body.features) {
        expect(feature.geometry.type, "reference geometry is points").toBe(
          "Point",
        );
        const [longitude, latitude] = feature.geometry.coordinates;
        expect(longitude).toBeGreaterThanOrEqual(-180);
        expect(longitude).toBeLessThanOrEqual(180);
        expect(latitude).toBeGreaterThanOrEqual(-90);
        expect(latitude).toBeLessThanOrEqual(90);
        expect(
          feature.properties.name,
          "every point says what it is",
        ).toBeTruthy();
        // Compare against the attribution the file declares for itself, so this
        // cannot fail on an encoding difference rather than on missing credit.
        expect(feature.properties.attribution).toBe(body.metadata.attribution);
        expect(body.metadata.attribution).toContain(
          "OpenStreetMap contributors",
        );
        // A blank country is left blank rather than guessed.
        if (feature.properties.country)
          expect(feature.properties.country).toMatch(/^[A-Z]{2}$/);
      }
    });

    test(`${id} loads in the panel and names its registry`, async ({
      page,
    }) => {
      await page.goto("/");
      await openLayerTopic(page, "places");
      await page.waitForSelector(`#layers input[data-layer='${id}']`);
      await page.locator(`#layers input[data-layer='${id}']`).check();
      await page.waitForTimeout(2500);
      const row = page.locator("#layers .layer-row", {
        has: page.locator(`[data-layer='${id}']`),
      });
      await expect(row.locator(".layer-count-reference")).toHaveText("ref");
      await expect(row.locator(".layer-note")).not.toContainText("Unavailable");
      await page.locator(`#layers button[data-layer-info='${id}']`).click();
      await page.waitForSelector("#reference-explanation");
      const fields = await page.$$eval("#reference-explanation dt", (labels) =>
        labels.map((label) => [
          label.textContent,
          label.nextElementSibling?.textContent,
        ]),
      );
      const lookup = Object.fromEntries(fields);
      expect(lookup.Publisher).toBe("OpenStreetMap contributors");
      expect(lookup.Licence).toBe("ODbL 1.0");
      expect(lookup.Limits).toBeTruthy();
      expect(lookup.Class).toContain("not an observation");
    });
  }

  test("the nuclear layer is facility-level, not one row per reactor", async ({
    request,
  }) => {
    const body = await (
      await request.get("/reference/nuclear-facilities.geojson")
    ).json();
    // Querying per-unit generator tags returns ~518 rows for roughly this many
    // plants, so a facility list must be far smaller than that. The earlier
    // per-unit query produced entries such as "(TAPS)-3" and "(TAPS)-4", which
    // would present one plant as several unrelated facilities.
    expect(body.features.length).toBeLessThan(300);
    const names = body.features.map((feature) =>
      feature.properties.name.toLowerCase(),
    );
    // Co-mapped duplicates are collapsed; a handful of genuinely separate
    // facilities sharing a name (Taishan 1 and 2) are legitimate.
    const unique = new Set(names);
    expect(body.features.length - unique.size).toBeLessThanOrEqual(5);
  });

  test("a military feature card names its publisher and licence", async ({
    page,
  }) => {
    await page.goto("/");
    await openLayerTopic(page, "places");
    await page.waitForFunction(
      () => document.querySelector("#map canvas")?.dataset.ready === "true",
      { timeout: 45000 },
    );
    await page.locator("#layers input[data-layer='bases']").check();
    await page.waitForFunction(
      () => document.querySelector("#map canvas")?.dataset.referenceHoverPoint,
      { timeout: 25000 },
    );
    let card = null;
    for (let attempt = 0; attempt < 12 && !card; attempt++) {
      const point = await page.evaluate(() => {
        const canvas = document.querySelector("#map canvas");
        const value = canvas.dataset.referenceHoverPoint;
        if (!value) return null;
        const [x, y] = value.split(",").map(Number);
        const rect = canvas.getBoundingClientRect();
        return { x: rect.x + x, y: rect.y + y };
      });
      if (!point) break;
      await page.mouse.move(point.x - 7, point.y - 7);
      await page.mouse.move(point.x, point.y);
      await page.waitForTimeout(220);
      card = await page.evaluate(() => {
        const el = document.querySelector(".event-hover-card");
        if (!el) return null;
        return {
          kind: el.querySelector(".hover-kind")?.textContent,
          title: el.querySelector("strong")?.textContent,
          fields: [...el.querySelectorAll("dt")].map(
            (dt, i) =>
              dt.textContent +
              " = " +
              el.querySelectorAll("dd")[i]?.textContent,
          ),
          caveat: el.querySelector(".hover-location")?.textContent,
          link: el.querySelector("a")?.href,
        };
      });
    }
    expect(card, "a military feature should answer hover").toBeTruthy();
    expect(card.title).toBeTruthy();
    expect(card.kind).toContain("not an observation");
    const fields = Object.fromEntries(card.fields.map((f) => f.split(" = ")));
    expect(fields.Source).toContain("OpenStreetMap");
    expect(fields.Licence).toBe("ODbL 1.0");
    // The closing line states what the point is not, not what it is.
    expect(card.caveat).toContain("not activity");
    expect(card.link).toContain("openstreetmap.org/copyright");
  });
});
