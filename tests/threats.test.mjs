import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildThreatNetwork,
  threatCountryActivity,
  threatTimeline,
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
