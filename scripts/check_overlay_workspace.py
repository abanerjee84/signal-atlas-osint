"""Verify new overlay controls against the running dashboard; starts no server."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--output", default="data/run/overlay-workspace")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    queries = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=args.chromium,
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.set_extra_http_headers(
            {"X-Forwarded-For": "2001:db8:" + ":".join(uuid4().hex[i : i + 4] for i in range(0, 24, 4))}
        )
        page.add_init_script(
            "sessionStorage.setItem('osint.layers',JSON.stringify(['space']));sessionStorage.setItem('osint.countryRibbonCollapsed','false')"
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: queries.append(request.url) if "/api/" in request.url else None)
        page.goto(args.url)
        page.wait_for_load_state("networkidle")
        expect(page.locator("#refresh")).to_be_enabled(timeout=45000)
        canvas = page.locator('canvas[data-ready="true"]')
        canvas.wait_for(timeout=30000)
        expect(page.locator('[data-count="space"]')).not_to_have_text("0")
        assert page.locator("input[data-layer]").count() == 10
        investigate = page.locator(".investigate-button")
        investigate.hover()
        expect(page.locator("#investigate-tooltip")).to_be_visible()
        assert investigate.get_attribute("href") == "/advanced.html"
        search = page.locator("#layer-search")
        for query, layer in [
            ("where are the planes", "aviation"),
            ("hacking and ransomware", "cyber"),
            ("oil prices", "economic"),
            ("international space station", "space"),
        ]:
            search.fill(query)
            expect(page.locator(f'.layer-row:visible input[data-layer="{layer}"]')).to_be_visible()
        search.fill("bananas")
        expect(page.locator("#layer-search-result")).to_contain_text("No related layers")
        assert page.locator(".layer-row:visible").count() == 0
        search.press("Escape")
        assert page.locator(".layer-row:visible").count() == 10
        assert page.locator('input[data-layer="space"]').is_checked()
        before = json.loads(canvas.get_attribute("data-orbital-positions"))
        page.wait_for_timeout(4500)
        after = json.loads(canvas.get_attribute("data-orbital-positions"))
        iss_before = next(item for item in before if item["id"] == "orbit-25544")
        iss = next(item for item in after if item["id"] == "orbit-25544")
        assert (
            abs(iss["longitude"] - iss_before["longitude"]) + abs(iss["latitude"] - iss_before["latitude"])
            > 0.05
        )
        bounds = canvas.bounding_box()
        gap = bounds["height"] - float(canvas.get_attribute("data-south-tip"))
        assert 12 <= gap <= 24, gap
        visible = next(
            item
            for item in after
            if 15 < item["x"] < bounds["width"] - 50 and 15 < item["y"] < bounds["height"] - 20
        )
        page.mouse.move(bounds["x"] + visible["x"], bounds["y"] + visible["y"])
        expect(page.locator(".map-hover-details")).to_contain_text("Altitude:")
        expect(page.locator(".map-hover-details")).to_contain_text("Calculated orbital position")
        page.screenshot(path=str(output / "hover.png"))
        page.locator('[data-event-id="orbit-25544"]').click()
        expect(page.locator("#event-detail")).to_contain_text("Orbital speed")
        expect(page.locator("#event-detail")).to_contain_text("NORAD catalogue")
        assert page.locator("#event-detail a").get_attribute("href").startswith("https://")
        assert not any("events/orbit-" in url or "categories=space" in url for url in queries)
        page.locator("#reset-view").click()
        page.screenshot(path=str(output / "desktop.png"))
        page.screenshot(path="docs/satellite-workspace.jpg", type="jpeg", quality=88)
        page.locator('[data-layer="space"]').uncheck()
        expect(canvas).to_have_attribute("data-orbital-positions", "[]")
        page.locator('[data-layer="space"]').check()
        expect(page.locator('[data-count="space"]')).not_to_have_text("0")
        page.locator("#playhead").fill("50")
        page.locator("#playhead").dispatch_event("input")
        expect(canvas).to_have_attribute("data-orbital-positions", "[]")
        page.locator("#playhead").fill("100")
        page.locator("#playhead").dispatch_event("input")
        expect(page.locator("#orbital-live-status")).to_be_visible()
        page.get_by_role("button", name="Analysis", exact=True).click()
        assert not page.locator("#ai-usage").count()
        assert "Each claim must cite stored source records" not in page.locator("#analysis-view").inner_text()
        assert "requests remain" not in page.locator("body").inner_text()
        page.set_viewport_size({"width": 800, "height": 900})
        expect(investigate).to_be_visible()
        investigate.focus()
        page.keyboard.press("Tab")
        page.keyboard.press("Shift+Tab")
        expect(page.locator("#investigate-tooltip")).to_be_visible()
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        assert not errors, errors
        result = {
            "satellites": len(after),
            "iss_movement_verified": True,
            "hover_details": True,
            "topic_search": True,
            "world_bottom_gap_px": gap,
            "internal_chatter_removed": True,
            "server_lifecycle_actions": 0,
            "errors": errors,
        }
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
