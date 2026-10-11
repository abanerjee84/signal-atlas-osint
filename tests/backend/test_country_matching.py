import re

import pytest

from backend.geo import country_matchers, mentioned_countries


def reference(text):
    text = re.sub(r"\b(?:Indian Ocean|British Columbia)\b", "", text, flags=re.I)
    codes = {code for code, pattern in country_matchers() if pattern.search(text)}
    for code, pattern in {"US": r"\bUS\b", "GB": r"\bUK\b", "AE": r"\bUAE\b"}.items():
        if re.search(pattern, text):
            codes.add(code)
    return sorted(codes)[:20]


@pytest.mark.parametrize(
    "text",
    [
        "Equatorial Guinea and Guinea-Bissau; South Korea and North Korea",
        "United States, U.S.A., U.S., USA; UK, U.K., UAE, US; help us",
        "Indian Ocean and British Columbia; British policy and Indian elections",
        "İndia, ındian, Kuwait, ſudan; Côte d’Ivoire and Türkiye",
        "China's policy and (Russian) reports; Chinese Taipei and Saudi Arabia",
        "FranceFrance, Germanness and xUnited Kingdom; French and Germany",
    ],
)
def test_matching_preserves_overlaps_boundaries_aliases_and_unicode(text):
    assert mentioned_countries(text) == reference(text)


def test_every_country_name_and_alias_preserves_original_matching():
    for _, pattern in country_matchers():
        names = pattern.pattern.removeprefix(r"(?<!\w)(?:").removesuffix(r")(?!\w)")
        for escaped in names.split("|"):
            name = re.sub(r"\\(.)", r"\1", escaped)
            for wording in [name, name.upper(), name.lower(), "(" + name + ")"]:
                assert mentioned_countries(wording) == reference(wording)
