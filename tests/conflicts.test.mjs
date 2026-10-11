import test from "node:test";
import assert from "node:assert/strict";
import { conflictType, conflictSummary } from "../src/conflicts.js";

test("conflict pictograms distinguish alerts, drones, rockets and artillery without changing unrelated layers", () => {
  for (const [title, id] of [
    ["Air raid sirens sound", "alert"],
    ["Drone attack reported", "drone"],
    ["Airstrikes reported", "airstrike"],
    ["Missile launch reported", "missile"],
    ["Artillery shelling reported", "shelling"],
    ["Bomb explosion reported", "explosion"],
    ["Troops deployment announced", "deployment"],
    ["Ceasefire negotiations resume", "diplomacy"],
  ])
    assert.equal(conflictType({ category: "military", title })?.id, id);
  assert.equal(
    conflictType({
      category: "geopolitical",
      title: "Workers on labour strike",
    }),
    null,
  );
  assert.equal(
    conflictType({ category: "geopolitical", title: "Earthquake in Myanmar" }),
    null,
  );
  assert.equal(
    conflictType({ category: "aviation", title: "Military aircraft" }),
    null,
  );
});

test("typed evidence wins over keyword guesses and summaries preserve source wording", () => {
  assert.equal(
    conflictType({
      category: "military",
      title: "Update",
      tags: ["conflict:naval"],
    })?.id,
    "naval",
  );
  assert.equal(
    conflictSummary({
      title: "Title",
      description: "<p>According to the source, an attack was reported.</p>",
    }),
    "According to the source, an attack was reported.",
  );
  assert.ok(
    conflictSummary({ description: "Source evidence. ".repeat(80) }).length <=
      360,
  );
  assert.equal(
    conflictSummary({ title: "Only the headline is available" }),
    "Only the headline is available",
  );
});
