import assert from "node:assert/strict";
import test from "node:test";
import { connectionGeometry, pointAlong } from "../src/geo-lines.js";

test("dateline connections remain finite and do not cross the entire map", () => {
  const geometry = connectionGeometry([170, 30], [-170, 40]);
  assert.equal(geometry.coordinates.length, 2);
  for (const line of geometry.coordinates)
    for (let i = 1; i < line.length; i++) {
      assert.ok(line[i].every(Number.isFinite));
      assert.ok(Math.abs(line[i][0] - line[i - 1][0]) <= 180);
    }
  assert.ok(Math.abs(pointAlong(geometry, 0)[0] - 170) < 1e-6);
  assert.ok(Math.abs(pointAlong(geometry, 1)[0] + 170) < 1e-6);
});
test("coincident and antipodal country anchors never produce NaN", () => {
  for (const [a, b] of [
    [
      [0, 0],
      [180, 0],
    ],
    [
      [12, 20],
      [12, 20],
    ],
    [
      [0, 89],
      [90, 89],
    ],
  ]) {
    const geometry = connectionGeometry(a, b);
    assert.ok(geometry.coordinates.flat(2).every(Number.isFinite));
    for (const t of [0, 0.25, 0.75, 1])
      assert.ok(pointAlong(geometry, t).every(Number.isFinite));
  }
});
