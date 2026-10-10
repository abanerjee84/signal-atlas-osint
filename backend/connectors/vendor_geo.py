"""Vendor country context at country centroids, never headquarters or incident coordinates."""

from functools import lru_cache

# Headquarters country for vendors that appear in bulk in NVD/CISA wording.
# Deliberately conservative: only vendors with a stable, publicly documented
# headquarters are listed. Unknown vendors resolve to no coordinates at all.
VENDOR_ORIGIN = {
    "microsoft": ("US", "Redmond, Washington, United States"),
    "ms": ("US", "Redmond, Washington, United States"),
    "windows": ("US", "Redmond, Washington, United States"),
    "apache": ("US", "Wilmington, Delaware, United States"),
    "apache software foundation": ("US", "Wilmington, Delaware, United States"),
    "cisco": ("US", "San Jose, California, United States"),
    "citrix": ("US", "Fort Lauderdale, Florida, United States"),
    "vmware": ("US", "Palo Alto, California, United States"),
    "broadcom": ("US", "Palo Alto, California, United States"),
    "oracle": ("US", "Austin, Texas, United States"),
    "adobe": ("US", "San Jose, California, United States"),
    "google": ("US", "Mountain View, California, United States"),
    "apple": ("US", "Cupertino, California, United States"),
    "meta": ("US", "Menlo Park, California, United States"),
    "facebook": ("US", "Menlo Park, California, United States"),
    "amazon": ("US", "Seattle, Washington, United States"),
    "aws": ("US", "Seattle, Washington, United States"),
    "netflix": ("US", "Los Gatos, California, United States"),
    "hp": ("US", "Spring, Texas, United States"),
    "hewlett-packard": ("US", "Spring, Texas, United States"),
    "ibm": ("US", "Armonk, New York, United States"),
    "dell": ("US", "Round Rock, Texas, United States"),
    "red hat": ("US", "Raleigh, North Carolina, United States"),
    "redhat": ("US", "Raleigh, North Carolina, United States"),
    "canonical": ("GB", "London, United Kingdom"),
    "ubuntu": ("GB", "London, United Kingdom"),
    "siemens": ("DE", "Munich, Germany"),
    "sap": ("DE", "Walldorf, Germany"),
    "bosch": ("DE", "Gerlingen, Germany"),
    "nokia": ("FI", "Espoo, Finland"),
    "ericsson": ("SE", "Stockholm, Sweden"),
    "dlink": ("TW", "Taipei, Taiwan"),
    "d-link": ("TW", "Taipei, Taiwan"),
    "zyxel": ("TW", "Hsinchu, Taiwan"),
    "huawei": ("CN", "Shenzhen, China"),
    "tencent": ("CN", "Shenzhen, China"),
    "alibaba": ("CN", "Hangzhou, China"),
    "samsung": ("KR", "Suwon, South Korea"),
    "lg": ("KR", "Seoul, South Korea"),
    "panasonic": ("JP", "Kadoma, Japan"),
    "fujitsu": ("JP", "Tokyo, Japan"),
    "nec": ("JP", "Tokyo, Japan"),
    "sony": ("JP", "Tokyo, Japan"),
    "trend micro": ("JP", "Tokyo, Japan"),
    "sophos": ("GB", "Abingdon, United Kingdom"),
    "avast": ("CZ", "Prague, Czech Republic"),
    "atlassian": ("AU", "Sydney, Australia"),
    "joomla": ("US", "Indianapolis, Indiana, United States"),
    "drupal": ("US", "Portland, Oregon, United States"),
    "strapi": ("FR", "Paris, France"),
    "ivanti": ("US", "Salt Lake City, Utah, United States"),
    "fortinet": ("US", "Sunnyvale, California, United States"),
    "palo alto networks": ("US", "Santa Clara, California, United States"),
    "atlassian bamboo": ("AU", "Sydney, Australia"),
    "nagios": ("US", "Saint Paul, Minnesota, United States"),
    "zimbra": ("US", "Irvine, California, United States"),
    "moodle": ("AU", "Perth, Australia"),
    "grafana": ("US", "New York, New York, United States"),
    "atlassian confluence": ("AU", "Sydney, Australia"),
    # Frequent in older CISA/NVD wording.
    "isc": ("US", "Redmond, Washington, United States"),
    "bind": ("US", "Redmond, Washington, United States"),
    "freebsd": ("US", "New York, New York, United States"),
    "openssl": ("GB", "London, United Kingdom"),
    "openssl project": ("GB", "London, United Kingdom"),
    "gnu": ("US", "Boston, Massachusetts, United States"),
    "wireshark": ("US", "Wireshark Foundation, Massachusetts, United States"),
    "talos": ("US", "Austin, Texas, United States"),
    "cisco systems": ("US", "San Jose, California, United States"),
    "juniper networks": ("US", "Sunnyvale, California, United States"),
    "juniper": ("US", "Sunnyvale, California, United States"),
    "progress software": ("US", "Bedford, Massachusetts, United States"),
    "atlassian jira": ("AU", "Sydney, Australia"),
    "confluence": ("AU", "Sydney, Australia"),
    "tomcat": ("US", "Wilmington, Delaware, United States"),
    "spring": ("US", "Wilmington, Delaware, United States"),
    "docker": ("US", "San Francisco, California, United States"),
    "kubernetes": ("US", "Seattle, Washington, United States"),
    "python software foundation": ("US", "Beaverton, Oregon, United States"),
}

BASIS = "Configured vendor country context at a country centroid; not headquarters, victim, attacker or exploitation coordinates"


@lru_cache(maxsize=1)
def country_centers() -> dict:
    """Country code to (longitude, latitude) centroid from the boundary file."""

    import json

    from ..config import ROOT

    countries = json.loads((ROOT / "public/countries.geojson").read_text(encoding="utf-8"))
    return {
        feature["properties"]["code"]: tuple(feature["properties"]["center"])
        for feature in countries["features"]
    }


def vendor_origin(vendor: str) -> tuple[float, float, str] | None:
    """Resolve a vendor string to (longitude, latitude, country code)."""

    if not vendor:
        return None
    key = vendor.strip().lower()
    if key in {"n/a", "unknown", "-", ""}:
        return None
    matched = VENDOR_ORIGIN.get(key)
    if not matched:
        # Fall back to the longest registered vendor name contained in the field,
        # so "apache http_server" still resolves to the Apache foundation.
        for candidate in sorted(VENDOR_ORIGIN, key=len, reverse=True):
            if len(candidate) >= 5 and candidate in key:
                matched = VENDOR_ORIGIN[candidate]
                break
    if not matched:
        return None
    country, _ = matched
    center = country_centers().get(country)
    if not center:
        return None
    return float(center[0]), float(center[1]), country
