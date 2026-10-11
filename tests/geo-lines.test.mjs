import assert from "node:assert/strict";
import test from "node:test";
import {
  connectionGeometry,
  straightConnectionGeometry,
  pointAlong,
} from "../src/geo-lines.js";

test("defence links stay straight in Mercator, including dateline crossings", () => {
  const project = ([x, lat]) => [
    x,
    Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)),
  ];
  for (const [a, b] of [
    [
      [-100, 38],
      [60, 60],
    ],
    [
      [170, -30],
      [-170, 70],
    ],
  ]) {
    const route = straightConnectionGeometry(a, b);
    const start = project(a);
    const points = route.coordinates
      .flat()
      .map(([x, y]) => project([x + 360 * Math.round((a[0] - x) / 360), y]));
    const end = points.at(-1);
    for (const p of points)
      assert.ok(
        Math.abs(
          (p[0] - start[0]) * (end[1] - start[1]) -
            (p[1] - start[1]) * (end[0] - start[0]),
        ) < 1e-7,
      );
    for (const line of route.coordinates)
      for (let i = 1; i < line.length; i++)
        assert.ok(Math.abs(line[i][0] - line[i - 1][0]) <= 180);
    assert.notDeepEqual(pointAlong(route, 0.4), pointAlong(route, 0.6));
  }
});
test("arrows keep advancing through the last segment instead of pausing", () => {
  const route = connectionGeometry([0, 0], [32, 0]);
  assert.notDeepEqual(pointAlong(route, 0.98), pointAlong(route, 0.99));
  assert.ok(pointAlong(route, 0.99)[0] < pointAlong(route, 1)[0]);
});

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
