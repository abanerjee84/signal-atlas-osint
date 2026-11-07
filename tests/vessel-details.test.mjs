import test from "node:test";
import assert from "node:assert/strict";
import {
  vesselRegistryFor,
  vesselRegistryRows,
} from "../src/vessel-details.js";
import { vesselFacts } from "../src/vessels.js";

test("registry lookup resolves by MMSI carried in tags", () => {
  const event = {
    category: "maritime",
    tags: ["ais", "232035583"],
    vessel_flag: "GB",
    vessel_type: 79,
    vessel_speed_kn: 12.5,
    vessel_course_deg: 217.8,
    time_key: "2026-10-10T12:00:00+00:00",
  };
  const registry = {
    "232035583": {
      mmsi: "232035583",
      shipname: "SYNTHETIC FERRY",
      callsign: "SYNTFX",
      imo: "1234567",
      flag: "GB",
      length_m: 150,
      tonnage_gt: 20000,
      types: ["Cargo"],
      owners: [{ name: "Example Shipping Ltd", flag: "GB", year_from: 2020 }],
      identity_basis: "registry_and_ais",
      updated_at: "2026-10-10T12:00:00+00:00",
    },
  };
  assert.equal(vesselRegistryFor(event, registry), registry["232035583"]);
});

test("non-vessel or missing MMSI returns null", () => {
  assert.equal(vesselRegistryFor({ tags: ["ais", "not-mmsi"] }), null);
  assert.equal(vesselRegistryFor({ tags: [] }), null);
  assert.equal(vesselRegistryFor({}), null);
});

test("registry rows add registry identity beyond AIS self-reporting", () => {
  const event = {
    tags: ["ais", "232035583"],
    vessel_flag: "GB",
    vessel_type: 79,
    vessel_speed_kn: 12.5,
    vessel_course_deg: 217.8,
    time_key: "2026-10-10T12:00:00+00:00",
  };
  const details = {
    mmsi: "232035583",
    shipname: "SYNTHETIC FERRY",
    owners: [{ name: "Example Shipping Ltd", flag: "GB", year_from: 2020 }],
    length_m: 150,
    tonnage_gt: 20000,
    types: ["Tanker"],
    updated_at: "2026-10-10T12:00:00+00:00",
  };
  const rows = vesselRegistryRows(event, details);
  assert.ok(rows.some(([label]) => label === "Registered as"));
  assert.ok(rows.some(([label]) => label === "Owner"));
  assert.ok(rows.some(([label]) => label === "Length"));
  assert.ok(rows.some(([label]) => label === "Tonnage"));
  assert.ok(rows.some(([label]) => label === "Registry classification"));
});

test("registry rows skip fields already present in the AIS self-report", () => {
  const event = {
    tags: ["ais", "232035583"],
    vessel_flag: "GB",
    vessel_type: 84,
    vessel_speed_kn: 12.5,
    vessel_course_deg: 217.8,
    time_key: "2026-10-10T12:00:00+00:00",
  };
  const details = {
    mmsi: "232035583",
    shipname: "SYNTHETIC FERRY",
    owners: [],
    length_m: null,
    tonnage_gt: null,
    types: ["Tanker"],
    updated_at: "2026-10-10T12:00:00+00:00",
  };
  const rows = vesselRegistryRows(event, details);
  assert.ok(rows.some(([label]) => label === "Registered as"));
  assert.ok(rows.every(([label]) => label !== "Length"));
  assert.ok(rows.every(([label]) => label !== "Tonnage"));
  assert.ok(rows.some(([label]) => label === "Registry classification"));
});

test("unavailable registry returns no rows", () => {
  const event = {
    tags: ["ais", "232035583"],
    vessel_flag: "GB",
    vessel_type: 79,
    vessel_speed_kn: 12.5,
    vessel_course_deg: 217.8,
    time_key: "2026-10-10T12:00:00+00:00",
  };
  assert.deepEqual(vesselRegistryRows(event, { available: false }), []);
  assert.deepEqual(vesselRegistryRows(event, null), []);
});
