import test from "node:test";
import assert from "node:assert/strict";
import {
  eligibleAircraft,
  latestAircraft,
  aircraftTransition,
  aircraftFacts,
} from "../src/aircraft.js";

const observation = {
  category: "aviation",
  aircraft_category: 4,
  aircraft_track_deg: 0,
  latitude: 20,
  longitude: 75,
  event_id: "new",
  tags: ["ads-b", "abcdef"],
  time_key: "2026-10-10T12:00:00+00:00",
};

test("only classes 4 and 5 with actual tracks qualify, including true north", () => {
  assert.equal(eligibleAircraft(observation), true);
  assert.equal(
    eligibleAircraft({
      ...observation,
      aircraft_category: 5,
      aircraft_track_deg: 359.9,
    }),
    true,
  );
  for (const aircraft_category of [null, 0, 1, 2, 3, 6, 7, 8])
    assert.equal(
      eligibleAircraft({ ...observation, aircraft_category }),
      false,
    );
  for (const aircraft_track_deg of [null, undefined, NaN, Infinity, -1, 360])
    assert.equal(
      eligibleAircraft({ ...observation, aircraft_track_deg }),
      false,
    );
  assert.equal(eligibleAircraft({ ...observation, latitude: null }), false);
});

test("short measured transitions cross the dateline and north by the shorter direction", () => {
  const old = { ...observation, longitude: 179.9, aircraft_track_deg: 359 };
  const next = {
    ...old,
    live: true,
    longitude: -179.9,
    aircraft_track_deg: 1,
    time_key: "2026-10-10T12:02:00+00:00",
  };
  const transition = aircraftTransition(old, next);
  assert.ok(transition);
  assert.equal(transition(0.5).longitude, -180);
  assert.equal(transition(0.5).aircraft_track_deg, 0);
  assert.equal(aircraftTransition(old, { ...next, live: false }), null);
  assert.equal(
    aircraftTransition(old, { ...next, time_key: "2026-10-10T13:00:00+00:00" }),
    null,
  );
  assert.equal(aircraftTransition(old, { ...next, longitude: 0 }), null);
  assert.equal(aircraftTransition(old, old), null);
});

test("aircraft facts preserve measured values and unknown origin", () => {
  const facts = aircraftFacts({
    ...observation,
    aircraft: {
      registration_country: "Synthetic",
      barometric_altitude_m: 10000,
      speed_mps: 250,
      on_ground: false,
    },
  });
  assert.match(facts["Barometric altitude"], /32,808 ft/);
  assert.match(facts["Ground speed"], /486 kt/);
  assert.equal(facts["Registration country"], "Synthetic");
  assert.equal(facts.Status, "Airborne");
  assert.equal(aircraftFacts(observation)["Barometric altitude"], "Unknown");
  assert.equal(aircraftFacts(observation)["Registration country"], "Unknown");
});

test("history draws the latest loaded position per transponder without changing track", () => {
  const old = {
    ...observation,
    event_id: "old",
    aircraft_track_deg: 180,
    time_key: "2026-10-10T11:00:00+00:00",
  };
  const other = {
    ...observation,
    event_id: "other",
    tags: ["ads-b", "fedcba"],
    aircraft_category: 5,
    aircraft_track_deg: 90,
  };
  assert.deepEqual(latestAircraft([observation, old, other]), [
    observation,
    other,
  ]);
});
