import math

RADIUS = 6371008.8


def coordinate(point):
    if not isinstance(point, (list, tuple)) or len(point) not in {2, 3}:
        raise ValueError("Coordinates must be WGS84 longitude, latitude pairs")
    if (
        any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in point)
        or not -180 <= point[0] <= 180
        or not -90 <= point[1] <= 90
    ):
        raise ValueError("Coordinates outside WGS84 bounds")
    return point


def validate_geojson(value):
    vertices = 0
    features = 0

    def geometry(g, depth=0):
        nonlocal vertices
        if depth > 4 or not isinstance(g, dict) or "crs" in g:
            raise ValueError("Only RFC 7946 WGS84 GeoJSON is accepted")
        kind = g.get("type")
        if kind == "GeometryCollection":
            items = g.get("geometries")
            if not isinstance(items, list) or len(items) > 200:
                raise ValueError("Invalid geometry collection")
            for item in items:
                geometry(item, depth + 1)
            return
        levels = {
            "Point": 0,
            "MultiPoint": 1,
            "LineString": 1,
            "MultiLineString": 2,
            "Polygon": 2,
            "MultiPolygon": 3,
        }
        if kind not in levels:
            raise ValueError("Unsupported GeoJSON geometry")

        def walk(items, depth):
            nonlocal vertices
            if depth == 0:
                coordinate(items)
                vertices += 1
                if vertices > 2000:
                    raise ValueError("Overlay exceeds 2000 coordinates")
            else:
                if not isinstance(items, list) or not items:
                    raise ValueError("Invalid coordinate nesting")
                for item in items:
                    walk(item, depth - 1)

        coords = g.get("coordinates")
        walk(coords, levels[kind])
        if kind == "LineString" and len(coords) < 2:
            raise ValueError("LineString needs two points")
        polygons = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
        for polygon in polygons:
            for ring in polygon:
                if len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError("Polygon rings must close with at least four coordinates")

    def visit(item, depth=0):
        nonlocal features
        if depth > 3 or not isinstance(item, dict) or "crs" in item:
            raise ValueError("Invalid RFC 7946 GeoJSON")
        if item.get("type") == "FeatureCollection":
            items = item.get("features")
            if not isinstance(items, list) or not items or len(items) > 200:
                raise ValueError("Use 1–200 features")
            for child in items:
                if child.get("type") != "Feature":
                    raise ValueError("FeatureCollection must contain Features")
                visit(child, depth + 1)
        elif item.get("type") == "Feature":
            features += 1
            if features > 200 or not isinstance(item.get("properties", {}), (dict, type(None))):
                raise ValueError("Invalid feature properties")
            geometry(item.get("geometry"))
        else:
            geometry(item)

    visit(value)
    return value


def distance(points):
    total = 0
    for left, right in zip(points, points[1:]):
        coordinate(left)
        coordinate(right)
        lon1, lat1, lon2, lat2 = map(math.radians, [*left[:2], *right[:2]])
        a = (
            math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        )
        total += 2 * RADIUS * math.asin(math.sqrt(min(1, max(0, a))))
    return total


def measure(operation, points):
    for point in points:
        coordinate(point)
    if operation == "distance":
        result, unit = distance(points), "meters"
    else:
        if len(points) < 4 or points[0] != points[-1]:
            raise ValueError("Area requires a closed polygon with at least four coordinates")
        total = 0
        for (lon1, lat1), (lon2, lat2) in zip(points, points[1:]):
            delta = (math.radians(lon2 - lon1) + math.pi) % (2 * math.pi) - math.pi
            total += delta * (2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
        result, unit = abs(total) * RADIUS**2 / 2, "square meters"
        result = min(result, 4 * math.pi * RADIUS**2 - result)
    return {
        "value": result,
        "unit": unit,
        "assumptions": "WGS84 lon/lat; spherical Earth radius 6371008.8 m; approximate great-circle distance or smaller spherical ring area, no terrain correction.",
    }
