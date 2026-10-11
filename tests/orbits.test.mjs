import test from "node:test";
import assert from "node:assert/strict";
import fixture from "./fixtures/orbital-elements.json" with { type: "json" };
import militaryFixture from "./fixtures/military-elements.json" with { type: "json" };
import {
  prepareOrbits,
  orbitalPositions,
  filterOrbitalPositions,
  orbitalTrajectories,
  splitGroundTrack,
  orbitalFacts,
  orbitalCountry,
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

test("military OMM and observer TLEs propagate with mission and tracking details", () => {
  const orbits = prepareOrbits(militaryFixture);
  const time = new Date(orbits[0].epoch);
  const positions = orbitalPositions(orbits, time);
  assert.equal(positions.length, 3);
  assert.ok(positions.every((item) => item.icon === "satellite-military"));
  const geo = positions.find((item) => item.name.startsWith("WGS"));
  assert.ok(geo.altitude_km > 35000 && geo.altitude_km < 37000);
  const later = orbitalPositions(orbits, new Date(time.getTime() + 60000)).find(
    (item) => item.catalog_id === geo.catalog_id,
  );
  assert.ok(Math.abs(later.longitude - geo.longitude) < 0.1);
  const facts = orbitalFacts(positions[0]);
  assert.equal(facts.Type, "Military");
  assert.ok(facts.Operator.includes("Germany"));
  assert.equal(facts["Country of origin"], "Germany");
  assert.equal(
    orbitalCountry({ operator_country: "INT" }),
    "International collaboration",
  );
  assert.equal(orbitalCountry({}), "Unknown");
  assert.ok(facts.Inclination.endsWith("°"));
});

test("ground tracks cross the dateline without spurious chords or joining missing positions", () => {
  const lines = splitGroundTrack([[179, 10], [-179, 12], null, [0, 0], [1, 1]]);
  assert.deepEqual(lines, [
    [
      [179, 10],
      [180, 11],
    ],
    [
      [-180, 11],
      [-179, 12],
    ],
    [
      [0, 0],
      [1, 1],
    ],
  ]);
  assert.deepEqual(
    splitGroundTrack([
      [-179, 10],
      [179, 12],
    ]),
    [
      [
        [-179, 10],
        [-180, 11],
      ],
      [
        [180, 11],
        [179, 12],
      ],
    ],
  );
  const orbits = prepareOrbits(fixture);
  const time = new Date(fixture.items[1].epoch);
  const tracks = orbitalTrajectories(orbits, time);
  assert.ok(tracks.features.length >= 2);
  assert.deepEqual(
    new Set(tracks.features.map((f) => f.properties.phase)),
    new Set(["past", "future"]),
  );
  for (const feature of tracks.features)
    for (const line of feature.geometry.coordinates) {
      assert.ok(line.length > 1);
      for (let i = 1; i < line.length; i++)
        assert.ok(Math.abs(line[i][0] - line[i - 1][0]) <= 180);
    }
  assert.equal(
    orbitalTrajectories(orbits, new Date(time.getTime() + 30 * 86400000))
      .features.length,
    0,
  );
});

test("military scope includes stations while navigation remains explicitly dual use", () => {
  const items = [
    { name: "ISS", role: "station" },
    { name: "WGS", role: "military", operator: "United States / Defence" },
    { name: "GPS", role: "navigation" },
    { name: "Hubble", role: "civil" },
  ];
  assert.deepEqual(
    filterOrbitalPositions(items, { scope: "defence" }).map((i) => i.name),
    ["ISS", "WGS"],
  );
  assert.deepEqual(
    filterOrbitalPositions(items, { scope: "military" }).map((i) => i.name),
    ["WGS"],
  );
  assert.deepEqual(
    filterOrbitalPositions(items, { scope: "navigation" }).map((i) => i.name),
    ["GPS"],
  );
  assert.deepEqual(
    filterOrbitalPositions(items, { q: "united states" }).map((i) => i.name),
    ["WGS"],
  );
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
