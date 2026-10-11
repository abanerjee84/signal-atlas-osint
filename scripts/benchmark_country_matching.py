"""Compare country extraction against the original matcher on retained reporting."""

import argparse
import json
import re
import time
from pathlib import Path

from backend.config import Settings
from backend.database import Database
from backend.geo import country_matchers, mentioned_countries


def reference(text):
    text = re.sub(r"\b(?:Indian Ocean|British Columbia)\b", "", text, flags=re.I)
    codes = {code for code, matcher in country_matchers() if matcher.search(text)}
    for code, pattern in {"US": r"\bUS\b", "GB": r"\bUK\b", "AE": r"\bUAE\b"}.items():
        if re.search(pattern, text):
            codes.add(code)
    return sorted(codes)[:20]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/run/country-matching-before.json")
    parser.add_argument("--require-speedup", action="store_true")
    args = parser.parse_args()
    database = Database(Settings().database)
    with database.connect() as db:
        texts = [
            r[0]
            for r in db.execute(
                "SELECT title||' '||description FROM reports WHERE sentiment_kind IS NOT NULL ORDER BY published_at DESC LIMIT 1000"
            )
        ]
    country_matchers()
    results, elapsed = {}, {}
    for name, matcher in [("reference", reference), ("current", mentioned_countries)]:
        start = time.perf_counter()
        results[name] = [matcher(text) for text in texts]
        elapsed[name] = time.perf_counter() - start
    assert results["reference"] == results["current"], "Country extraction changed"
    result = {
        "report_count": len(texts),
        "same_countries": True,
        "seconds": elapsed,
        "speedup": elapsed["reference"] / elapsed["current"],
        "server_lifecycle_actions": 0,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if args.require_speedup:
        assert result["speedup"] >= 3, "Country matching remains slow"


if __name__ == "__main__":
    main()
