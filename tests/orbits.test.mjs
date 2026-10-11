import test from "node:test";
import assert from "node:assert/strict";
import fixture from "./fixtures/orbital-elements.json" with { type: "json" };
import {
  prepareOrbits,
  orbitalPositions,
  filterOrbitalPositions,
} from "../src/orbits.js";
import { searchLayers } from "../src/layer-search.js";

test("ISS propagation produces plausible, changing positions from public elements", () => {
  const orbits = prepareOrbits(fixture);
  const epoch = new Date(
    fixture.items.find((item) => item.catalog_id === 25544).epoch,
  );
  const first = orbitalPositions(orbits, epoch).find(
    (item) => item.catalog_id === 25544,
  );
  const later = orbitalPositions(
    orbits,
    new Date(epoch.getTime() + 60000),
  ).find((item) => item.catalog_id === 25544);
  assert.ok(first.altitude_km > 300 && first.altitude_km < 500);
  assert.ok(first.speed_kms > 7 && first.speed_kms < 8);
  assert.ok(
    Math.abs(first.longitude - later.longitude) +
      Math.abs(first.latitude - later.latitude) >
      0.5,
  );
  assert.ok(Math.abs(first.latitude) < 52);
  assert.equal(first.icon, "iss");
  assert.equal(
    orbitalPositions(orbits, new Date(epoch.getTime() + 30 * 86400000)).length,
    0,
  );
  assert.equal(orbitalPositions(orbits, new Date(NaN)).length, 0);
  assert.equal(prepareOrbits({ items: [{ epoch: "invalid" }] }).length, 0);
});

test("satellite geographic filters include polygon holes and wrapped viewports", () => {
  const items = [
    {
      name: "ISS",
      purpose: "Space station",
      catalog_id: 25544,
      latitude: 5,
      longitude: 5,
    },
    { name: "Hubble", purpose: "Space telescope", latitude: 1, longitude: 1 },
    { name: "Aqua", purpose: "Earth observation", latitude: 1, longitude: 175 },
  ];
  const world = {
    features: [
      {
        properties: { code: "XX" },
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [0, 0],
              [10, 0],
              [10, 10],
              [0, 10],
              [0, 0],
            ],
            [
              [4, 4],
              [6, 4],
              [6, 6],
              [4, 6],
              [4, 4],
            ],
          ],
        },
      },
    ],
  };
  assert.deepEqual(
    filterOrbitalPositions(items, { country: "XX", world }).map(
      (item) => item.name,
    ),
    ["Hubble"],
  );
  assert.deepEqual(
    filterOrbitalPositions(items, { bbox: [170, -10, -170, 10] }).map(
      (item) => item.name,
    ),
    ["Aqua"],
  );
  assert.deepEqual(
    filterOrbitalPositions(items, { q: "space station" }).map(
      (item) => item.name,
    ),
    ["ISS"],
  );
  assert.deepEqual(
    filterOrbitalPositions(items, { country: "unknown", world }),
    [],
  );
});

test("layer concepts find related topics without requiring a layer's title", () => {
  assert.equal(searchLayers("where are the planes", {})[0], "aviation");
  assert.equal(searchLayers("hacking and ransomware", {})[0], "cyber");
  assert.equal(searchLayers("oil prices", {})[0], "economic");
  assert.equal(searchLayers("international space station", {})[0], "space");
  assert.equal(searchLayers("public opinion reddit", {})[0], "sentiment");
  assert.deepEqual(searchLayers("bananas", {}), []);
  assert.deepEqual(
    searchLayers("", { aviation: "Aviation", threat: "Cyber" }),
    ["aviation"],
  );
});
