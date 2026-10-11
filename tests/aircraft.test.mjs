import test from "node:test";
import assert from "node:assert/strict";
import {
  AIRCRAFT_FILTERS,
  eligibleAircraft,
  isRotorcraft,
  latestAircraft,
  aircraftTransition,
  aircraftFacts,
  aircraftTransponderId,
  recordTrailPoints,
  trailLine,
  trailSamples,
  matchesAircraftFilter,
  filterLiveAircraft,
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

test("any reported class with an actual track qualifies, including true north", () => {
  assert.equal(eligibleAircraft(observation), true);
  for (const aircraft_category of [...Array(21).keys(), null])
    assert.equal(
      eligibleAircraft({ ...observation, aircraft_category }),
      true,
      `class ${aircraft_category} should qualify`,
    );
  assert.equal(
    eligibleAircraft({
      ...observation,
      aircraft_category: 5,
      aircraft_track_deg: 359.9,
    }),
    true,
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

test("rotorcraft are identified by the provider class or a known type code", () => {
  // Class 8 is the provider's own Rotorcraft value.
  assert.equal(isRotorcraft({ aircraft_category: 8 }), true);
  assert.equal(
    isRotorcraft({ aircraft_category: 4 }, { type_code: "EC45" }),
    true,
  );
  for (const type_code of [
    "AS350",
    "EC135",
    "AW139",
    "R44",
    "BK117",
    "UH60",
    "S76",
  ])
    assert.equal(
      isRotorcraft({ aircraft_category: 0 }, { type_code }),
      true,
      type_code,
    );
  // Fixed-wing designs that merely share a leading character must not match.
  for (const type_code of [
    "B738",
    "A320",
    "A20N",
    "C172",
    "MD82",
    "SR22",
    "SB50",
    "EC45",
  ])
    assert.equal(
      isRotorcraft({ aircraft_category: 0 }, { type_code }),
      type_code === "EC45",
      type_code,
    );
  assert.equal(isRotorcraft({ aircraft_category: 0 }), false);
  assert.equal(isRotorcraft({ aircraft_category: 0 }, {}), false);
  assert.equal(
    isRotorcraft({ aircraft_category: 0 }, { type_code: null }),
    false,
  );
});

test("a trail merges ordered history with live positions and drops repeats", () => {
  const at = (hex, time_key, longitude, latitude, extra = {}) => ({
    ...observation,
    event_id: `${hex}-${time_key}`,
    tags: ["ads-b", hex],
    time_key,
    longitude,
    latitude,
    ...extra,
  });
  const history = [
    at("abcdef", "2026-10-10T12:00:00+00:00", 10, 50),
    at("abcdef", "2026-10-10T12:30:00+00:00", 11, 51),
    at("abcdef", "2026-10-10T11:00:00+00:00", 9, 49),
    at("fedcba", "2026-10-10T12:15:00+00:00", 40, -20),
  ];
  const samples = trailSamples(
    history.filter((event) => aircraftTransponderId(event) === "abcdef"),
  );
  assert.equal(aircraftTransponderId(history[3]), "fedcba");
  assert.deepEqual(samples, [
    ["2026-10-10T11:00:00+00:00", 9, 49],
    ["2026-10-10T12:00:00+00:00", 10, 50],
    ["2026-10-10T12:30:00+00:00", 11, 51],
  ]);
  // An unlocated or trackless observation is not a point on a path.
  assert.deepEqual(
    trailSamples([history[1], { ...history[1], latitude: null }]),
    [["2026-10-10T12:30:00+00:00", 11, 51]],
  );

  const store = new Map();
  recordTrailPoints(store, [history[2], history[0], history[1]]);
  // A repeat of the same observation must not double a point.
  recordTrailPoints(store, [history[1]]);
  // An out-of-order arrival is dropped rather than bending the path.
  recordTrailPoints(store, [history[0], history[3]]);
  assert.equal(store.get("abcdef").length, 3);
  assert.equal(store.get("fedcba").length, 1);
  const live = [
    ["2026-10-10T12:30:00+00:00", 11, 51],
    ["2026-10-10T12:31:00+00:00", 12, 52],
  ];
  // The shared instant appears once, and history leads.
  assert.deepEqual(trailLine(samples, live), [
    [9, 49],
    [10, 50],
    [11, 51],
    [12, 52],
  ]);
  assert.deepEqual(trailLine(live, samples), trailLine(samples, live));

  // The oldest samples fall outside the cap.
  const long = Array.from({ length: 70 }, (_, index) =>
    at(
      "abcdef",
      `2026-10-10T${String(Math.floor(index / 60)).padStart(2, "0")}:${String(index % 60).padStart(2, "0")}:00+00:00`,
      index,
      50,
    ),
  );
  assert.equal(recordTrailPoints(new Map(), long, 60).get("abcdef").length, 60);
  assert.equal(recordTrailPoints(new Map(), long).get("abcdef").length, 70);
});

test("selector leads with the military flag, then all classes and every provider class", () => {
  const values = AIRCRAFT_FILTERS.map(([value]) => value);
  assert.equal(new Set(values).size, values.length);
  assert.equal(values[0], "military");
  assert.equal(values[1], "all");
  for (const value of [...Array(21).keys()].map(String))
    assert.ok(values.includes(value), `missing class ${value}`);
  for (const [value] of AIRCRAFT_FILTERS)
    assert.equal(
      matchesAircraftFilter({ ...observation, aircraft_category: 12 }, value),
      value === "all" || value === "12",
      `class 12 against ${value}`,
    );
});

test("class and military filters use measured class and explicit registry identity", () => {
  const event = {
    ...observation,
    aircraft_category: 2,
    aircraft: { icao24: "abcdef" },
  };
  assert.equal(eligibleAircraft(event, "all"), true);
  assert.equal(matchesAircraftFilter(event, "2"), true);
  assert.equal(matchesAircraftFilter(event, "3"), false);
  assert.equal(
    matchesAircraftFilter(event, "military", {
      abcdef: { icao24: "abcdef", military: true },
    }),
    true,
  );
  for (const record of [
    { military: true },
    { icao24: "bbbbbb", military: true },
    { icao24: "abcdef", military: false },
  ])
    assert.equal(
      matchesAircraftFilter(event, "military", { abcdef: record }),
      false,
    );
  assert.equal(
    matchesAircraftFilter(
      { ...event, title: "MILITARY US AIR FORCE" },
      "military",
    ),
    false,
  );
  assert.equal(
    matchesAircraftFilter({ ...event, category: "military" }, "2"),
    true,
  );
});

test("live file snapshots respect geographic focus, dates and dateline bounds", () => {
  const event = {
    ...observation,
    aircraft_category: 1,
    country_code: "IN",
    title: "Aircraft TEST1",
    description: "ICAO abcdef",
  };
  assert.deepEqual(filterLiveAircraft([event], { country: "IN", q: "test1" }), [
    event,
  ]);
  assert.deepEqual(filterLiveAircraft([event], { country: "US" }), []);
  assert.deepEqual(
    filterLiveAircraft([event], { start: "2026-10-10T12:00:01Z" }),
    [],
  );
  assert.deepEqual(
    filterLiveAircraft([event], { end: "2026-10-10T11:59:59Z" }),
    [],
  );
  assert.deepEqual(filterLiveAircraft([event], { bbox: [70, 10, 80, 30] }), [
    event,
  ]);
  assert.deepEqual(
    filterLiveAircraft([event], { bbox: [170, -30, -170, 30] }),
    [],
  );
  assert.equal(
    filterLiveAircraft([{ ...event, longitude: -179 }], {
      bbox: [170, -30, -170, 30],
    }).length,
    1,
  );
  assert.deepEqual(
    filterLiveAircraft([{ ...event, aircraft_track_deg: null }], {}),
    [],
  );
});
