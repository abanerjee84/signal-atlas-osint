import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildThreatNetwork,
  threatCountryActivity,
  threatTimeline,
  threatFacts,
  threatCaption,
} from "../src/threats.js";

const places = [
  { code: "RU", center: [100, 60] },
  { code: "UA", center: [32, 49] },
  { code: "US", center: [-100, 40] },
];
const report = {
  event_id: "one",
  title: "Russian hackers target Ukraine",
  description: "Published report",
  source_url: "https://example.org/report",
  tags: ["actor:APT28", "attributed-country:RU", "victim-country:UA"],
};
test("daily requests stay separate from incident counts and reporting periods", () => {
  const sample = (id, period, requests) => ({
    ...report,
    event_id: id,
    source_id: "imperva_threatmap",
    tags: [
      "threat-classification:observed_traffic",
      "traffic-origin-country:US",
      "traffic-target-country:RU",
      "attack-kind:OWASP",
      "daily-aggregate",
      `reporting-period:${period}`,
      `provider-requests:${requests}`,
    ],
  });
  const first = sample("daily1", "2026-10-08 to 2026-10-09", 81);
  const network = buildThreatNetwork(
    [
      first,
      sample("daily2", "2026-10-08 to 2026-10-09", 200),
      sample("daily3", "2026-10-09 to 2026-10-10", 10),
    ],
    places,
  );
  assert.equal(network.edges.length, 2);
  assert.equal(network.edges[0].count, 2);
  assert.equal(network.edges[0].request_count, 281);
  assert.equal(network.observation_count, 0);
  assert.equal(network.aggregate_count, 3);
  assert.match(threatCaption(threatFacts(first)), /81 provider requests/);
});

test("traffic is directed separately, counted by observation ID, and not attributed to an actor", () => {
  const detection = {
    ...report,
    event_id: "packet1",
    source_id: "bunkerweb_threatmap",
    tags: [
      "threat-classification:observed_traffic",
      "traffic-origin-country:RU",
      "traffic-target-country:UA",
    ],
  };
  const network = buildThreatNetwork(
    [detection, { ...detection, event_id: "packet2" }, detection, report],
    places,
  );
  const traffic = network.edges.find(
    (edge) => edge.kind === "observed_traffic_to_target",
  );
  assert.equal(traffic.count, 2);
  assert.equal(traffic.from, "RU");
  assert.equal(traffic.to, "UA");
  assert.equal(network.edges.length, 2);
  assert.equal(network.unknown_origin_count, 0);
  assert.equal(network.report_count, 1);
  assert.equal(threatFacts(detection).attacker_country, null);
  assert.match(threatCaption(threatFacts(detection)), /Actor unknown/);
  const point = {
    ...detection,
    tags: ["threat-classification:detection", "detection-country:US"],
  };
  assert.equal(
    buildThreatNetwork([point], places, { country: "US" }).edges.length,
    0,
  );
  assert.equal(
    buildThreatNetwork([point], places, { country: "UA" }).events.length,
    0,
  );
});

test("one cyber layer combines country coverage and timeline without duplicate layer counts", () => {
  const row = { ...report, time_key: "2026-10-11T02:31:00Z" };
  const network = buildThreatNetwork([row], places);
  const layers = new Set(["cyber", "threat"]);
  const ranking = threatCountryActivity(
    {
      items: [
        {
          country: "RU",
          mentions: 1,
          mention_sources: 1,
          records: 1,
          intelligence_records: 1,
          supported_records: 0,
          categories: { cyber: 1 },
          layer_count: 1,
        },
      ],
      methodology: { mentions: "", intelligence: "" },
    },
    network,
    places,
    layers,
  );
  const origin = ranking.items.find((item) => item.country === "RU");
  assert.equal(origin.layer_count, 1);
  assert.equal(origin.categories.cyber, 2);
  assert.equal(origin.categories.threat, undefined);
  const timeline = threatTimeline(
    {
      time_basis: "event",
      items: [{ time: "2026-10-11T02:00:00", category: "cyber", count: 2 }],
    },
    network,
    layers,
  );
  assert.equal(timeline.items.length, 1);
  assert.equal(timeline.items[0].count, 3);
});

test("only explicit attributed origin and victim tags create a directional edge", () => {
  const result = buildThreatNetwork(
    [
      report,
      { ...report, event_id: "duplicate" },
      {
        ...report,
        event_id: "unknown",
        source_url: "https://example.org/unknown",
        tags: ["actor:Lazarus", "victim-country:UA"],
      },
    ],
    places,
  );
  assert.equal(result.edges.length, 1);
  assert.equal(result.edges[0].from, "RU");
  assert.equal(result.edges[0].to, "UA");
  assert.equal(result.edges[0].count, 1);
  assert.equal(result.unknown_origin_count, 1);
});

test("threat-only country rankings and timeline exclude fallback social activity", () => {
  const event = {
    ...report,
    source_id: "research",
    time_key: "2026-10-11T02:31:00Z",
  };
  const network = buildThreatNetwork(
    [event, { ...event, event_id: "duplicate" }],
    places,
  );
  const ranking = threatCountryActivity(
    {
      items: [
        {
          country: "US",
          mentions: 99,
          mention_sources: 3,
          records: 99,
          intelligence_records: 10,
          supported_records: 0,
          layer_count: 1,
          categories: { geopolitical: 10 },
        },
      ],
      methodology: { mentions: "Report context.", intelligence: "Coverage." },
    },
    network,
    places,
    new Set(["threat"]),
  );
  assert.equal(ranking.items.find((item) => item.country === "US").mentions, 0);
  const origin = ranking.items.find((item) => item.country === "RU");
  assert.equal(origin.mentions, 1);
  assert.equal(origin.categories.threat, 1);
  assert.equal(origin.mention_sources, 1);
  assert.equal(origin.supported_records, 0);
  const history = threatTimeline(
    {
      time_basis: "event",
      items: [
        { time: "2026-10-11T02:00:00", category: "sentiment", count: 99 },
      ],
    },
    network,
    new Set(["threat"]),
  );
  assert.equal(history.items.length, 1);
  assert.equal(history.items[0].category, "threat");
  assert.equal(history.items[0].count, 2);
});

test("country and viewport selection consider either role without inventing a position", () => {
  assert.equal(
    buildThreatNetwork([report], places, { country: "RU" }).report_count,
    1,
  );
  assert.equal(
    buildThreatNetwork([report], places, { country: "US" }).report_count,
    0,
  );
  assert.equal(
    buildThreatNetwork([report], places, { bbox: [20, 45, 40, 55] }).edges
      .length,
    1,
  );
  assert.equal(
    buildThreatNetwork([report], places, { q: "ransomware" }).report_count,
    0,
  );
});
