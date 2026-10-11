// Illustrative shortest great-circle connections, split at the map's dateline.
const radians = (value) => (value * Math.PI) / 180;
const degrees = (value) => (value * 180) / Math.PI;
const normalize = (value) => ((value + 540) % 360) - 180;
const routeSegments = new WeakMap();
export function connectionGeometry(from, to) {
  const vector = ([lon, lat]) => [
    Math.cos(radians(lat)) * Math.cos(radians(lon)),
    Math.cos(radians(lat)) * Math.sin(radians(lon)),
    Math.sin(radians(lat)),
  ];
  const a = vector(from),
    b = vector(to),
    dot = Math.max(
      -1,
      Math.min(
        1,
        a.reduce((sum, v, i) => sum + v * b[i], 0),
      ),
    ),
    angle = Math.acos(dot);
  const points = [];
  for (let step = 0; step <= 32; step++) {
    const t = step / 32;
    if (Math.abs(Math.sin(angle)) < 1e-8)
      points.push([
        normalize(from[0] + normalize(to[0] - from[0]) * t),
        from[1] + (to[1] - from[1]) * t,
      ]);
    else {
      const x = a.map(
        (v, i) =>
          (Math.sin((1 - t) * angle) * v + Math.sin(t * angle) * b[i]) /
          Math.sin(angle),
      );
      points.push([
        degrees(Math.atan2(x[1], x[0])),
        degrees(Math.atan2(x[2], Math.hypot(x[0], x[1]))),
      ]);
    }
  }
  return splitAtDateline(points);
}

// Straight in the dashboard's Mercator map, with short steps so report pulses
// follow the displayed link. Wrap at the dateline instead of spanning the world.
export function straightConnectionGeometry(from, to) {
  const mercator = (lat) =>
    Math.log(
      Math.tan(Math.PI / 4 + radians(Math.max(-85, Math.min(85, lat))) / 2),
    );
  const start = mercator(from[1]);
  const end = mercator(to[1]);
  const delta = normalize(to[0] - from[0]);
  const points = Array.from({ length: 33 }, (_, step) => {
    const t = step / 32;
    return [
      normalize(from[0] + delta * t),
      degrees(2 * Math.atan(Math.exp(start + (end - start) * t)) - Math.PI / 2),
    ];
  });
  return splitAtDateline(points, (a, b, t) =>
    degrees(
      2 * Math.atan(Math.exp(mercator(a) + (mercator(b) - mercator(a)) * t)) -
        Math.PI / 2,
    ),
  );
}

function splitAtDateline(points, latitudeAt = (a, b, t) => a + t * (b - a)) {
  const segments = [[points[0]]];
  for (let i = 1; i < points.length; i++) {
    const previous = points[i - 1],
      current = points[i];
    if (Math.abs(current[0] - previous[0]) > 180) {
      const boundary = previous[0] > 0 ? 180 : -180;
      const unwrapped = current[0] + (previous[0] > 0 ? 360 : -360);
      const ratio = (boundary - previous[0]) / (unwrapped - previous[0]);
      const lat = latitudeAt(previous[1], current[1], ratio);
      segments.at(-1).push([boundary, lat]);
      segments.push([[-boundary, lat], current]);
    } else segments.at(-1).push(current);
  }
  return { type: "MultiLineString", coordinates: segments };
}

export function pointAlong(geometry, progress) {
  let segments = routeSegments.get(geometry);
  if (!segments) {
    segments = geometry.coordinates.flatMap((line) =>
      line.slice(1).map((point, i) => [line[i], point]),
    );
    routeSegments.set(geometry, segments);
  }
  const position = Math.min(
    segments.length,
    Math.max(0, progress * segments.length),
  );
  const index = Math.min(segments.length - 1, Math.floor(position));
  const fraction = progress >= 1 ? 1 : position - index;
  const [from, to] = segments[index];
  return [
    from[0] + (to[0] - from[0]) * fraction,
    from[1] + (to[1] - from[1]) * fraction,
  ];
}
