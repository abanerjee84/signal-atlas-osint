"""Verify real vectors and source evidence on the existing app; never starts a server."""

import argparse
import json
import re
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--output", default="data/run/attack-vector-browser")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=args.chromium,
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        token = uuid4().hex[:24]
        page.set_extra_http_headers(
            {"X-Forwarded-For": "2001:db8:" + ":".join(token[i : i + 4] for i in range(0, 24, 4))}
        )
        page.add_init_script(
            "sessionStorage.setItem('osint.layers',JSON.stringify(['threat']));sessionStorage.setItem('osint.countryRibbonCollapsed','false')"
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.wait_for_load_state("networkidle")
        expect(page.locator("#refresh")).to_be_enabled(timeout=45000)
        page.wait_for_selector('canvas[data-ready="true"]', timeout=30000)
        page.locator("#period").select_option("168")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#refresh")).to_be_enabled(timeout=45000)
        page.locator('[data-country-rank="cyber"]').click()
        expect(page.locator("#radware-vector-panel")).to_be_visible()
        expect(page.locator("#radware-vector-body")).to_contain_text("TCP Flood", timeout=45000)
        expect(page.locator("#radware-vector-body")).to_contain_text("not linked to individual country pairs")
        initial_routes = page.locator("[data-threat-route]").count()
        assert initial_routes > 0
        page.locator("#cyber-vector-filter").select_option("known")
        known_routes = page.locator("[data-threat-route]").count()
        assert 0 < known_routes < initial_routes
        assert "BLACKLIST" not in page.locator("#country-ranking").inner_text()
        assert "Not specified by provider" not in page.locator("#country-ranking").inner_text()
        # The real retained Imperva sample contains supplied RCE/RFI labels.
        page.locator("#cyber-route-source").select_option("imperva_threatmap")
        routes = page.locator("[data-threat-route]")
        assert routes.count() > 0
        expect(routes.first).to_contain_text("Vector / type:")
        routes.first.click()
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("Vector / type:")
        assert "Not specified by provider" not in page.locator(".maplibregl-popup-content").inner_text()
        page.screenshot(path=str(output / "known-vectors.png"))
        page.screenshot(path="docs/threat-actor-workspace.jpg", type="jpeg", quality=88)
        page.locator("#cyber-vector-filter").select_option("Phishing")
        # Reports with unknown attribution still appear as evidence cards.
        cards = page.locator(".event-button").filter(has_text="Threat Actor")
        assert cards.count() > 0
        primary = cards.filter(has_text=re.compile("THREAT_RESEARCH_", re.I))
        assert primary.count() > 0, "No scraped primary article in the selected period and vector"
        primary.first.click()
        expect(page.locator("#event-detail")).to_be_visible()
        expect(page.locator("#event-detail")).to_contain_text("Known attack vectors")
        expect(page.locator("#event-detail")).to_contain_text("Vector evidence")
        expect(page.locator("#event-detail")).to_contain_text("Phishing")
        assert page.locator("#event-detail a[target='_blank']").count() > 0
        page.screenshot(path=str(output / "technique-evidence.png"))
        result = {
            "initial_routes": initial_routes,
            "known_routes": known_routes,
            "specific_vectors_filter": True,
            "research_evidence_details": True,
            "global_radware_methods_separate": True,
            "errors": errors,
            "server_lifecycle_actions": 0,
        }
        assert not errors, errors
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
