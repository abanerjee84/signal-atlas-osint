"""Country assignment from Natural Earth 1:110m boundaries. Not suitable for boundary disputes."""

import json
from functools import lru_cache

from .config import ROOT


@lru_cache(maxsize=1)
def countries() -> dict:
    return json.loads((ROOT / "public/countries.geojson").read_text(encoding="utf-8"))


def in_ring(x: float, y: float, ring: list) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous[:2]
        x2, y2 = current[:2]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


@lru_cache(maxsize=1)
def polygons() -> list:
    result = []
    for feature in countries()["features"]:
        geometry = feature["geometry"]
        parts = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for rings in parts:
            xs, ys = zip(*[(point[0], point[1]) for point in rings[0]])
            result.append((feature["properties"]["code"], (min(xs), min(ys), max(xs), max(ys)), rings))
    return result


def country_at(longitude: float, latitude: float) -> str | None:
    for code, (west, south, east, north), rings in polygons():
        if west <= longitude <= east and south <= latitude <= north:
            if in_ring(longitude, latitude, rings[0]) and not any(
                in_ring(longitude, latitude, hole) for hole in rings[1:]
            ):
                return code
    return None


def named_country(title: str) -> dict | None:
    """Only whole country names in a title; a regional mention, never an event location."""

    matches = mentioned_countries(title)
    return (
        next(
            (
                feature["properties"]
                for feature in countries()["features"]
                if feature["properties"]["code"] == matches[0]
            ),
            None,
        )
        if len(matches) == 1
        else None
    )


@lru_cache(maxsize=1)
def country_matchers():
    import re

    aliases = {
        "US": ["United States", "USA", "U.S.A.", "U.S."],
        "GB": ["United Kingdom", "UK", "U.K.", "Britain", "British"],
        "KR": ["South Korea", "South Korean"],
        "KP": ["North Korea", "North Korean"],
        "RU": ["Russian"],
        "UA": ["Ukrainian"],
        "CN": ["Chinese"],
        "IL": ["Israeli"],
        "PS": ["Palestine", "Palestinian", "Gaza", "West Bank"],
        "IR": ["Iranian"],
        "DE": ["German"],
        "FR": ["French"],
        "IN": ["Indian"],
        "PK": ["Pakistani"],
        "TR": ["Türkiye", "Turkish"],
        "SY": ["Syrian"],
        "LB": ["Lebanese"],
        "AF": ["Afghan"],
        "JP": ["Japanese"],
        "CA": ["Canadian"],
        "AU": ["Australian"],
        "SA": ["Saudi", "Saudi Arabia"],
        "KW": ["Kuwaiti"],
        "OM": ["Omani"],
    }
    result = []
    for feature in countries()["features"]:
        props = feature["properties"]
        names = [props["name"], *aliases.get(props["code"], [])]
        pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(name) for name in names) + r")(?!\w)", re.I)
        result.append((props["code"], pattern))
    return result


def mentioned_countries(text: str) -> list[str]:
    """Country/nationality discussion keywords, never a poster's residence."""
    import re

    # These common place names are not mentions of those countries.
    text = re.sub(r"\b(?:Indian Ocean|British Columbia)\b", "", text, flags=re.I)
    codes = {code for code, matcher in country_matchers() if matcher.search(text)}
    for code, pattern in {"US": r"\bUS\b", "GB": r"\bUK\b", "AE": r"\bUAE\b"}.items():
        if re.search(pattern, text):
            codes.add(code)
    return sorted(codes)[:20]


def unique_country_context(text: str) -> dict | None:
    """A single explicitly named country is context, never actor attribution."""
    codes = mentioned_countries(text)
    if len(codes) != 1:
        return None
    return next(
        (
            feature["properties"]
            for feature in countries()["features"]
            if feature["properties"]["code"] == codes[0]
        ),
        None,
    )
