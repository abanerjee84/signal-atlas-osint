import test from "node:test";
import assert from "node:assert/strict";
import {
  eligibleVessel,
  latestVessel,
  vesselFacts,
  vesselFlagName,
  vesselId,
  vesselSummary,
  vesselTypeLabel,
} from "../src/vessels.js";

const observation = {
  category: "maritime",
  vessel_course_deg: 217.8,
  latitude: 50.9,
  longitude: -1.3,
  event_id: "vessel",
  tags: ["ais", "232035583"],
  title: "Vessel Synthetic Ferry",
  vessel_speed_kn: 12.5,
  vessel_type: 79,
  vessel_flag: "GB",
  time_key: "2026-10-10T12:00:00+00:00",
};

test("a flagged, typed vessel presents registration and self-reported family", () => {
  const facts = vesselFacts(observation);
  assert.equal(facts["Flag state"], "United Kingdom");
  assert.equal(facts["Vessel type"], "79 · Cargo");
  assert.equal(facts.Name, "Synthetic Ferry");
  assert.equal(facts.MMSI, "232035583");
});

test("the type label names the known family with the code beside it", () => {
  assert.equal(vesselTypeLabel(20), "20 · Wing in ground");
  assert.equal(vesselTypeLabel(31), "31 · Towing");
  assert.equal(vesselTypeLabel(40), "40 · High-speed craft");
  assert.equal(vesselTypeLabel(55), "55 · Law enforcement");
  assert.equal(vesselTypeLabel(70), "70 · Cargo");
  assert.equal(vesselTypeLabel(84), "84 · Tanker");
  // Codes below the 20–99 families are reserved bands but still reportable.
  assert.equal(vesselTypeLabel(4), "4 · Reserved");
  assert.equal(vesselTypeLabel(17), "17 · Reserved");
  assert.equal(vesselTypeLabel(0), null);
  assert.equal(vesselTypeLabel(255), "255 · Reserved");
  assert.equal(vesselTypeLabel(9.5), null);
  assert.equal(vesselTypeLabel(null), null);
});

test("the flag name only resolves valid registration codes", () => {
  assert.equal(vesselFlagName("PA"), "Panama");
  assert.equal(vesselFlagName("GB"), "United Kingdom");
  assert.equal(vesselFlagName("XX"), null);
  assert.equal(vesselFlagName(null), null);
  assert.equal(vesselFlagName(undefined), null);
});

test("vessels without registration or type keep unknown slots", () => {
  const facts = vesselFacts({
    ...observation,
    title: "Vessel 232035583",
    vessel_flag: null,
    vessel_type: null,
  });
  assert.equal(facts.Name, "Unnamed");
  assert.equal(facts["Flag state"], "Unknown");
  assert.equal(facts["Vessel type"], "Unknown");
});

test("the summary carries flag and family so map glyphs read fully", () => {
  assert.equal(
    vesselSummary(observation),
    "Synthetic Ferry · United Kingdom · 79 · Cargo · 12.5 kn · 23 km/h · Course 218°",
  );
});

test("eligibility and identity keep their keyed behaviour", () => {
  assert.equal(eligibleVessel(observation), true);
  assert.equal(vesselId(observation), "232035583");
  const older = {
    ...observation,
    time_key: "2026-10-10T11:00:00+00:00",
    event_id: "older",
  };
  assert.equal(
    latestVessel([older, observation]).every(
      (event) => event.event_id === "vessel",
    ),
    true,
  );
});
