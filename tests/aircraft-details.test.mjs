import test from "node:test";
import assert from "node:assert/strict";
import {
  matchedAircraftDetails,
  trustedAircraftPhoto,
} from "../src/aircraft-details.js";
import { aircraftMotionDuration } from "../src/aircraft.js";

test("an aircraft photo cannot attach to a reused callsign on a different hex", () => {
  const event = {
    aircraft: { icao24: "ABCDEF" },
    aircraft_callsign: "TEST123",
  };
  const detail = {
    icao24: "abcdef",
    callsign: "TEST123",
    registration: "N123",
  };
  assert.equal(matchedAircraftDetails(event, detail), detail);
  assert.equal(
    matchedAircraftDetails(event, { ...detail, icao24: "aaaaaa" }),
    null,
  );
  assert.equal(
    matchedAircraftDetails(event, { ...detail, callsign: "OTHER" }),
    null,
  );
});
test("aircraft images permit only the credited photo provider", () => {
  const photo = {
    url: "https://t.plnspttrs.net/123/photo.jpg",
    link: "https://www.planespotters.net/photo/123",
    credit: "Photographer",
  };
  assert.equal(trustedAircraftPhoto(photo), photo);
  assert.equal(
    trustedAircraftPhoto({
      ...photo,
      url: "https://t.plnspttrs.net.attacker.example/x",
    }),
    null,
  );
  assert.equal(
    trustedAircraftPhoto({ ...photo, url: "https://user@t.plnspttrs.net/x" }),
    null,
  );
  assert.equal(trustedAircraftPhoto({ ...photo, credit: "" }), null);
});
test("observed position interpolation fills the 30 second cadence without extrapolation", () => {
  const previous = { time_key: "2026-10-11T15:00:00Z" };
  assert.equal(
    aircraftMotionDuration(previous, { time_key: "2026-10-11T15:00:30Z" }),
    30000,
  );
  assert.equal(
    aircraftMotionDuration(previous, { time_key: "2026-10-11T15:02:00Z" }),
    30000,
  );
  assert.equal(
    aircraftMotionDuration(previous, { time_key: "2026-10-11T15:00:05Z" }),
    8000,
  );
});
