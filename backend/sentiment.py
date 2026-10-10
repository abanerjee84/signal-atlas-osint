"""Deterministic English headline lexicon, deliberately limited and disclosed."""

import re
from functools import lru_cache

POSITIVE = set(
    "agreement aid approve breakthrough ceasefire cooperation growth improve peace recovery relief rescue stability success support truce win".split()
)
NEGATIVE = set(
    "attack crisis dead death decline disaster dispute disruption drought escalates explosion famine fear fire flood killed loss outage protest recession sanctions threat violence war wounded".split()
)
STOP = set(
    "the a an of on in to for and or with as is are by from at after over says said new this that its it has have will not amid".split()
)


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9-]{2,}", text.lower())) - STOP


def score(text: str, language: str) -> tuple[str | None, float | None]:
    if language.lower() not in {"english", "en", "eng"}:
        return None, None
    words = tokens(text)
    positive, negative = len(words & POSITIVE), len(words & NEGATIVE)
    value = (positive - negative) / max(1, positive + negative)
    return ("positive" if value > 0 else "negative" if value < 0 else "neutral"), value


@lru_cache(maxsize=1)
def social_analyzer():
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    return SentimentIntensityAnalyzer()


def social_score(text: str, language: str) -> tuple[str | None, float | None]:
    if language.lower() not in {"english", "en", "eng"}:
        return None, None
    value = social_analyzer().polarity_scores(text)["compound"]
    return ("positive" if value >= 0.05 else "negative" if value <= -0.05 else "neutral"), value


def detect_language(text: str) -> str:
    from langdetect import DetectorFactory, LangDetectException, detect_langs

    DetectorFactory.seed = 0
    if len(re.findall(r"\w+", text)) < 5:
        return "unknown"
    try:
        result = detect_langs(text[:2000])[0]
        return result.lang if result.prob >= 0.8 else "unknown"
    except LangDetectException:
        return "unknown"
