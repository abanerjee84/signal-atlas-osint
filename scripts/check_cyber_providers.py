import json
import re
import ssl
import time
from pathlib import Path

import httpx

with httpx.Client(verify=ssl.create_default_context(), timeout=25, follow_redirects=False) as client:
    text = client.get("https://api.ioda.inetintel.cc.gatech.edu/v2/").text
    specification = json.loads(
        re.search(r'<script id="swagger-data".*?>(.*?)</script>', text, re.S).group(1)
    )["spec"]
    for path, item in specification["paths"].items():
        if "outages/events" in path or "outages/summary" in path:
            print(path)
            print(json.dumps(item["get"].get("parameters"), indent=2)[:8000])
    end = int(time.time())
    for url in [
        f"https://api.ioda.inetintel.cc.gatech.edu/v2/outages/events?from={end - 86400}&until={end}&entityType=country&limit=10",
        "https://stat.ripe.net/data/network-info/data.json?resource=8.8.8.8&sourceapp=GlobalOSINT",
    ]:
        response = client.get(url)
        print(response.status_code, response.text[:2500])
    Path("docs/ioda-provider-spec.json").write_text(json.dumps(specification, indent=2), encoding="utf-8")
