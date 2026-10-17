"""Explicit technique wording only; a blacklist verdict is not an attack vector."""

import json
import re
from pathlib import Path

RULES = json.loads(
    (Path(__file__).resolve().parents[1] / "src/attack-vectors.json").read_text(encoding="utf-8")
)


def extract_vectors(text, *, contextual=True):
    text = re.sub(r"\s+", " ", text.replace("–", "-").replace("‑", "-")).strip()[:20000]
    vectors, evidence = [], []
    for rule in RULES:
        for match in re.finditer(rule["pattern"], text, re.I):
            prefix = re.split(r"[.!?;]", text[max(0, match.start() - 100) : match.start()])[-1]
            if contextual and re.search(
                r"\b(?:not|no evidence of|no signs of|without|prevent|protect against|mitigat(?:e|ing)|hypothetical)\b",
                prefix,
                re.I,
            ):
                continue
            vectors.append(rule["label"])
            evidence.append(text[max(0, match.start() - 35) : match.end() + 55].strip())
            break
    if any(
        label in vectors
        for label in [
            "TCP flood",
            "IP flood",
            "UDP flood",
            "HTTP flood",
            "HTTPS flood",
            "DNS amplification",
            "Low-and-slow attack",
        ]
    ):
        vectors = [v for v in vectors if v != "DDoS (subtype unspecified)"]
    return vectors[:12], " | ".join(dict.fromkeys(evidence))[:800]


def reputation_reason(label):
    return bool(
        re.search(
            r"\b(?:blacklist|dnsbl|blocklist|reputation|bad[- _]?(?:ip|behavior)|anonymizer|TOR|country|geoip|geoblock|antibot|crowdsec|modsecurity|unknown|default|limit)\b",
            label,
            re.I,
        )
        or re.search(r"\blocal[- _]activit", label, re.I)
    )
