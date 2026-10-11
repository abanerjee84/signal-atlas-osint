import { connectionGeometry, pointAlong } from "./geo-lines.js";

export function routeBearing(from, to) {
  const radians = (value) => (value * Math.PI) / 180;
  const a = radians(from[1]),
    b = radians(to[1]),
    delta = radians(to[0] - from[0]);
  return (
    ((Math.atan2(
      Math.sin(delta) * Math.cos(b),
      Math.cos(a) * Math.sin(b) - Math.sin(a) * Math.cos(b) * Math.cos(delta),
    ) *
      180) /
      Math.PI +
      360) %
    360
  );
}

export function cyberRouteFeatures(network) {
  const nodes = new Map(),
    arrows = [];
  for (const edge of network?.edges || []) {
    for (const [role, country, coordinates] of [
      ["origin", edge.from, edge.from_coordinates],
      ["target", edge.to, edge.to_coordinates],
    ]) {
      const key = `${role}:${country}`;
      const node = nodes.get(key) || {
        type: "Feature",
        geometry: { type: "Point", coordinates },
        properties: { role, country, count: 0, event_id: edge.event_ids[0] },
      };
      node.properties.count += edge.count;
      nodes.set(key, node);
    }
    if (edge.domestic || edge.from === edge.to) continue;
    const geometry = connectionGeometry(
      edge.from_coordinates,
      edge.to_coordinates,
    );
    for (const progress of [0.3, 0.6, 0.88]) {
      const coordinates = pointAlong(geometry, progress);
      const next = pointAlong(geometry, progress + 0.01);
      arrows.push({
        type: "Feature",
        geometry: { type: "Point", coordinates },
        properties: {
          id: edge.id,
          kind: edge.kind,
          rotation: routeBearing(coordinates, next),
        },
      });
    }
  }
  return {
    endpoints: { type: "FeatureCollection", features: [...nodes.values()] },
    arrows: { type: "FeatureCollection", features: arrows },
  };
}
