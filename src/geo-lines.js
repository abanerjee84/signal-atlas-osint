// Illustrative shortest great-circle connections, split at the map's dateline.
const radians = (value) => (value * Math.PI) / 180;
const degrees = (value) => (value * 180) / Math.PI;
const normalize = (value) => ((value + 540) % 360) - 180;
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
  const segments = [[points[0]]];
  for (let i = 1; i < points.length; i++) {
    const previous = points[i - 1],
      current = points[i];
    if (Math.abs(current[0] - previous[0]) > 180) {
      const boundary = previous[0] > 0 ? 180 : -180;
      const unwrapped = current[0] + (previous[0] > 0 ? 360 : -360);
      const ratio = (boundary - previous[0]) / (unwrapped - previous[0]);
      const lat = previous[1] + ratio * (current[1] - previous[1]);
      segments.at(-1).push([boundary, lat]);
      segments.push([[-boundary, lat], current]);
    } else segments.at(-1).push(current);
  }
  return { type: "MultiLineString", coordinates: segments };
}

export function pointAlong(geometry, progress) {
  const segments = geometry.coordinates.flatMap((line) =>
    line.slice(1).map((point, i) => [line[i], point]),
  );
  const position = Math.min(
    segments.length - 1,
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
