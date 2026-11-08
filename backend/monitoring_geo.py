"""Bounded WGS84 geometry and spatial predicates, without invented coordinates."""

import math


def geometry(value, max_vertices=10000):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"type", "coordinates", "bbox"}:
        raise ValueError("Expected a WGS84 geometry")
    kind = value.get("type")
    depths = {
        "Point": 0,
        "MultiPoint": 1,
        "LineString": 1,
        "MultiLineString": 2,
        "Polygon": 2,
        "MultiPolygon": 3,
    }
    if kind not in depths:
        raise ValueError("Unsupported geometry type")
    count = 0

    def check(values, depth):
        nonlocal count
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError("Empty geometry")
        if depth == 0:
            if len(values) < 2 or any(type(v) not in {int, float} or not math.isfinite(v) for v in values):
                raise ValueError("Invalid coordinate")
            if not -180 <= values[0] <= 180 or not -90 <= values[1] <= 90:
                raise ValueError("Coordinate outside WGS84")
            count += 1
            if count > max_vertices:
                raise ValueError("Geometry exceeds vertex budget")
            return list(values[:2])
        return [check(v, depth - 1) for v in values]

    coords = check(value.get("coordinates"), depths[kind])
    lines = [coords] if kind == "LineString" else coords if kind == "MultiLineString" else []
    if any(len(line) < 2 for line in lines):
        raise ValueError("A line needs two positions")
    polys = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
    if any(len(ring) < 4 or ring[0] != ring[-1] for poly in polys for ring in poly):
        raise ValueError("Polygon rings must be closed")
    return {"type": kind, "coordinates": coords}


def points(g):
    if not g:
        return []

    def walk(value):
        if value and isinstance(value[0], (int, float)):
            yield value[:2]
        else:
            for part in value:
                yield from walk(part)

    return list(walk(g["coordinates"]))


def distance(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, [*a, *b])
    v = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, v))))


def _unwrap(x, origin):
    return origin + (x - origin + 180) % 360 - 180


def _ring(point, ring):
    x, y = _unwrap(point[0], ring[0][0]), point[1]
    unwrapped = [ring[0]]
    for vertex in ring[1:]:
        unwrapped.append([_unwrap(vertex[0], unwrapped[-1][0]), vertex[1]])
    inside = False
    for a, b in zip(unwrapped, unwrapped[1:]):
        ax, bx = a[0], b[0]
        if (
            abs((bx - ax) * (y - a[1]) - (b[1] - a[1]) * (x - ax)) < 1e-9
            and min(ax, bx) - 1e-9 <= x <= max(ax, bx) + 1e-9
            and min(a[1], b[1]) - 1e-9 <= y <= max(a[1], b[1]) + 1e-9
        ):
            return True
        if (a[1] > y) != (b[1] > y) and x < (bx - ax) * (y - a[1]) / (b[1] - a[1]) + ax:
            inside = not inside
    return inside


def contains(g, point):
    if g["type"] == "Polygon":
        poly = g["coordinates"]
        return _ring(point, poly[0]) and not any(_ring(point, hole) for hole in poly[1:])
    if g["type"] == "MultiPolygon":
        return any(contains({"type": "Polygon", "coordinates": p}, point) for p in g["coordinates"])
    return False


def segments(g):
    c, kind = g["coordinates"], g["type"]
    lines = (
        [c]
        if kind == "LineString"
        else c
        if kind in {"MultiLineString", "Polygon"}
        else [ring for p in c for ring in p]
        if kind == "MultiPolygon"
        else []
    )
    return [(a, b) for line in lines for a, b in zip(line, line[1:])]


def segment_distance(point, a, b):
    """Shortest great-circle distance to a minor-arc segment, in km."""
    angular = distance(a, point) / 6371.0088
    length = distance(a, b) / 6371.0088
    if length < 1e-10:
        return distance(point, a)

    def bearing(p, q):
        x1, y1, x2, y2 = map(math.radians, [*p, *q])
        return math.atan2(
            math.sin(x2 - x1) * math.cos(y2),
            math.cos(y1) * math.sin(y2) - math.sin(y1) * math.cos(y2) * math.cos(x2 - x1),
        )

    diff = bearing(a, point) - bearing(a, b)
    cross = math.asin(max(-1, min(1, math.sin(angular) * math.sin(diff))))
    along = math.atan2(math.sin(angular) * math.cos(diff), math.cos(angular))
    return abs(cross) * 6371.0088 if 0 <= along <= length else min(distance(point, a), distance(point, b))


def near(point, g, radius_km=0):
    if contains(g, point):
        return True
    if g["type"] in {"Point", "MultiPoint"}:
        return any(distance(point, p) <= radius_km for p in points(g))
    return any(segment_distance(point, a, b) <= radius_km for a, b in segments(g))


def intersects(a, b):
    pa, pb = points(a), points(b)
    # Conservative rejection; wide/dateline geometries still take the exact path below.
    if (
        pa
        and pb
        and max(p[0] for p in pa) - min(p[0] for p in pa) < 180
        and max(p[0] for p in pb) - min(p[0] for p in pb) < 180
    ):
        if (
            max(p[0] for p in pa) < min(p[0] for p in pb)
            or max(p[0] for p in pb) < min(p[0] for p in pa)
            or max(p[1] for p in pa) < min(p[1] for p in pb)
            or max(p[1] for p in pb) < min(p[1] for p in pa)
        ):
            return False
    if any(contains(a, p) for p in points(b)) or any(contains(b, p) for p in points(a)):
        return True

    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    for p, q in segments(a):
        for r, s in segments(b):
            origin = p[0]
            p1, q1, r1, s1 = [[_unwrap(v[0], origin), v[1]] for v in [p, q, r, s]]
            v1, v2, v3, v4 = cross(p1, q1, r1), cross(p1, q1, s1), cross(r1, s1, p1), cross(r1, s1, q1)
            if (
                v1 * v2 <= 0
                and v3 * v4 <= 0
                and all(
                    max(min(p1[i], q1[i]), min(r1[i], s1[i]))
                    <= min(max(p1[i], q1[i]), max(r1[i], s1[i])) + 1e-9
                    for i in [0, 1]
                )
            ):
                return True
    return False


def geometry_distance(a, b):
    if intersects(a, b):
        return 0.0
    pa, pb = points(a), points(b)
    sa, sb = segments(a), segments(b)
    return min(
        [distance(p, q) for p in pa for q in pb]
        + [segment_distance(p, u, v) for p in pa for u, v in sb]
        + [segment_distance(p, u, v) for p in pb for u, v in sa]
    )


def possibly_near(a, b, radius_km):
    pa, pb = points(a), points(b)
    if not pa or not pb:
        return False
    lowa, higha = min(p[1] for p in pa), max(p[1] for p in pa)
    lowb, highb = min(p[1] for p in pb), max(p[1] for p in pb)
    if max(lowa, lowb) - min(higha, highb) > radius_km / 110:
        return False
    la, ha = min(p[0] for p in pa), max(p[0] for p in pa)
    lb, hb = min(p[0] for p in pb), max(p[0] for p in pb)
    if ha - la > 180 or hb - lb > 180:
        return True
    gap = min(max(la, lb + shift) - min(ha, hb + shift) for shift in [-360, 0, 360])
    lat = max(abs(v) for v in [lowa, higha, lowb, highb])
    return gap <= radius_km / (110 * max(0.001, math.cos(math.radians(lat))))
