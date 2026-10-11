import { test } from "node:test";
import assert from "node:assert/strict";
import { cyberRouteFeatures, routeBearing } from "../src/cyber-routes.js";
import { buildThreatNetwork } from "../src/threats.js";

test("every displayed route arrow advances between animation frames", () => {
  const network = {
    edges: [
      {
        id: "moving",
        from: "DE",
        to: "US",
        from_coordinates: [10, 51],
        to_coordinates: [-100, 40],
        count: 1,
        event_ids: ["one"],
        kind: "observed_traffic_to_target",
      },
    ],
  };
  const first = cyberRouteFeatures(network, 0).arrows.features;
  const next = cyberRouteFeatures(network, 0.1).arrows.features;
  assert.equal(first.length, next.length);
  for (let i = 0; i < first.length; i++)
    assert.notDeepEqual(
      first[i].geometry.coordinates,
      next[i].geometry.coordinates,
    );
});

test("direction bearings point towards the target, including the dateline", () => {
  for (const [from, to, expected] of [
    [[0, 0], [0, 10], 0],
    [[0, 0], [10, 0], 90],
    [[0, 0], [0, -10], 180],
    [[0, 0], [-10, 0], 270],
    [[175, 0], [-175, 0], 90],
  ])
    assert.ok(Math.abs(routeBearing(from, to) - expected) < 0.001);
  const edge = {
    id: "dateline",
    from: "X",
    to: "Y",
    from_coordinates: [175, 0],
    to_coordinates: [-175, 0],
    count: 1,
    event_ids: ["one"],
    kind: "observed_traffic_to_target",
  };
  const { arrows } = cyberRouteFeatures({ edges: [edge] });
  assert.equal(arrows.features.length, 3);
  for (const arrow of arrows.features) {
    assert.equal(arrow.properties.id, edge.id);
    assert.equal(arrow.properties.kind, edge.kind);
    assert.ok(Math.abs(arrow.properties.rotation - 90) < 0.001);
    assert.ok(Math.abs(arrow.geometry.coordinates[0]) >= 175);
  }
});

test("same-country detections keep both roles without fabricating an outward arrow", () => {
  const places = [
    { code: "DE", center: [10, 51] },
    { code: "US", center: [-100, 40] },
  ];
  const report = (id, from) => ({
    event_id: id,
    source_id: "bunkerweb_threatmap",
    tags: [
      "threat-classification:observed_traffic",
      `traffic-origin-country:${from}`,
      "traffic-target-country:DE",
    ],
  });
  const network = buildThreatNetwork(
    [report("one", "DE"), report("two", "US")],
    places,
  );
  assert.equal(network.edges.length, 2);
  const domestic = network.edges.find((edge) => edge.domestic);
  assert.equal(domestic.from, "DE");
  assert.equal(domestic.to, "DE");
  const { arrows, endpoints } = cyberRouteFeatures(network);
  assert.equal(arrows.features.length, 3);
  assert.ok(
    arrows.features.every((feature) => feature.properties.id !== domestic.id),
  );
  assert.equal(endpoints.features.length, 3);
  const german = endpoints.features.filter(
    (feature) => feature.properties.country === "DE",
  );
  assert.deepEqual(
    new Set(german.map((feature) => feature.properties.role)),
    new Set(["origin", "target"]),
  );
  assert.equal(
    german.find((feature) => feature.properties.role === "target").properties
      .count,
    2,
  );
});
