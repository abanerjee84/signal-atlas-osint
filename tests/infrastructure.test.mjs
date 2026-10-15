import test from "node:test";
import assert from "node:assert/strict";
import {
  infrastructureFacts,
  infrastructureSummary,
} from "../src/infrastructure.js";
import { searchLayers } from "../src/layer-search.js";
import { CATEGORY_NAMES } from "../src/layer-symbols.js";

test("map facts preserve aggregate units and parse MapLibre JSON properties", () => {
  const record = {
    source_id: "dshield",
    cyber_observation: JSON.stringify({
      indicator_value: "8.8.8.8",
      report_count: 12,
      target_count: 3,
      received_at: "2026-10-15T00:00:00Z",
      source_family: "sans_isc",
    }),
    infrastructure_geo: JSON.stringify({
      country_code: "US",
      retrieved_at: "2026-10-15T00:00:00Z",
    }),
  };
  const facts = new Map(infrastructureFacts(record));
  assert.equal(facts.get("Provider reports"), "12");
  assert.equal(facts.get("Target hosts"), "3");
  assert.equal(facts.get("Infrastructure country"), "US");
  assert(!facts.has("Actor") && !facts.has("Victim"));
  assert.equal(
    infrastructureSummary(record),
    "12 provider reports · 3 target hosts",
  );
});

test("unlocated indicators remain unknown and layer topic search discovers infrastructure", () => {
  const facts = new Map(
    infrastructureFacts({
      cyber_observation: { indicator_value: "example.org" },
    }),
  );
  assert.equal(
    facts.get("Infrastructure country"),
    "Unknown; no supported location",
  );
  assert(
    searchLayers("DShield IP honeypots", CATEGORY_NAMES).includes(
      "infrastructure",
    ),
  );
});
