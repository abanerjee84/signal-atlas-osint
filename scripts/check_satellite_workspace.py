"""Verify satellite presentation on existing servers; never starts a server."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--output", default="data/run/satellite-workspace")
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
        page.add_init_script("sessionStorage.setItem('osint.layers',JSON.stringify(['space']));")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)

        def expose_map(route):
            response = route.fetch()
            text = response.text()
            original = "worldMap = createWorldMap(state.world, {"
            assert original in text
            # Test-only access; no diagnostic global is shipped in the product.
            route.fulfill(
                response=response,
                body=text.replace(
                    original, "worldMap = window.satelliteTest = createWorldMap(state.world, {", 1
                ),
            )

        page.route("**/src/main.js*", expose_map)
        page.goto(args.url)
        page.wait_for_load_state("networkidle")
        expect(page.locator("#refresh")).to_be_enabled(timeout=45000)
        page.wait_for_function("!document.querySelector('#refresh-time').textContent.includes('Waiting')")
        canvas = page.locator('canvas[data-ready="true"]')
        canvas.wait_for(timeout=45000)
        expect(page.locator("#orbital-controls")).to_be_visible()
        expect(page.locator('[data-count="space"]')).not_to_have_text("0")
        page.wait_for_function(
            "window.satelliteTest?.map.queryRenderedFeatures({layers:['orbital-labels']}).length > 10"
        )

        def positions():
            return json.loads(canvas.get_attribute("data-orbital-positions"))

        first = positions()
        assert len(first) > 60
        assert {item["role"] for item in first} == {"military", "station"}
        label_count = page.evaluate(
            "window.satelliteTest.map.queryRenderedFeatures({layers:['orbital-labels']}).length"
        )
        assert page.locator('.orbital-card .event-title img[alt="United States"]').count() > 20
        assert page.locator('.orbital-card .event-title img[alt="International collaboration"]').count() == 1
        assert page.evaluate(
            "Array.from(document.querySelectorAll('.orbital-card .event-title')).every(n => n.firstChild.nodeType === Node.TEXT_NODE && n.lastChild.tagName === 'IMG')"
        )
        page.screenshot(path="docs/satellite-workspace.jpg", type="jpeg", quality=90)
        page.evaluate("""() => {
            const source = window.satelliteTest.map.getSource('orbital-tracks');
            const original = source.setData.bind(source);
            window.trackUpdates = 0;
            source.setData = (...args) => { window.trackUpdates++; return original(...args); };
        }""")
        page.wait_for_timeout(4500)
        later = positions()
        before_iss = next(item for item in first if item["id"] == "orbit-25544")
        after_iss = next(item for item in later if item["id"] == "orbit-25544")
        movement = abs(after_iss["longitude"] - before_iss["longitude"]) + abs(
            after_iss["latitude"] - before_iss["latitude"]
        )
        assert movement > 0.05
        assert page.evaluate("window.trackUpdates") <= 1
        bounds = canvas.bounding_box()
        visible = page.evaluate("""() => {
            const map = window.satelliteTest.map;
            return map.queryRenderedFeatures({layers:['orbital-positions']})
                .filter(f => f.properties.role === 'military' && f.properties.operator_country)
                .map(f => ({...f.properties, ...map.project(f.geometry.coordinates)}))
                .find(f => f.x > 250 && f.x < map.getCanvas().clientWidth-80 && f.y > 180 && f.y < map.getCanvas().clientHeight-120);
        }""")
        assert visible
        page.mouse.move(bounds["x"] + visible["x"], bounds["y"] + visible["y"])
        tooltip = page.locator(".orbital-hover-card")
        expect(tooltip).to_be_visible()
        expect(tooltip).to_contain_text("Country of origin:")
        expect(tooltip).to_contain_text("Altitude:")
        expect(tooltip).to_contain_text("Tracking basis:")
        expect(tooltip).to_contain_text("Calculated orbital position")
        assert tooltip.evaluate(
            "n => { const p = n.closest('.maplibregl-popup-content'); return p.scrollHeight <= p.clientHeight; }"
        )
        assert tooltip.locator("strong img").get_attribute("alt") != "Unknown"
        highlighted = page.evaluate("window.satelliteTest.map.getFilter('orbital-track-highlight')[2]")
        assert highlighted.startswith("orbit-")
        page.screenshot(path="docs/satellite-hover.jpg", type="jpeg", quality=90)
        page.mouse.move(10, 10)
        page.locator("#orbital-tracks").uncheck()
        expect(canvas).to_have_attribute("data-orbital-tracks", "0")
        page.locator("#orbital-tracks").check()
        expect(canvas).not_to_have_attribute("data-orbital-tracks", "0")
        page.locator("#orbital-scope").select_option("all")
        page.wait_for_function("document.querySelector('[data-count=space]').textContent > 100")
        all_count = len(positions())
        page.locator("#orbital-scope").select_option("navigation")
        assert {item["role"] for item in positions()} == {"navigation"}
        navigation_count = len(positions())
        page.locator("#orbital-scope").select_option("military")
        assert {item["role"] for item in positions()} == {"military"}
        military_count = len(positions())
        page.locator("#playhead").fill("50")
        page.locator("#playhead").dispatch_event("input")
        expect(canvas).to_have_attribute("data-orbital-positions", "[]")
        expect(canvas).to_have_attribute("data-orbital-tracks", "0")
        page.locator("#playhead").fill("100")
        page.locator("#playhead").dispatch_event("input")
        page.locator('[data-layer="space"]').uncheck()
        expect(page.locator("#orbital-controls")).to_be_hidden()
        expect(canvas).to_have_attribute("data-orbital-positions", "[]")
        assert not errors, errors
        result = {
            "all_spacecraft": all_count,
            "military": military_count,
            "navigation": navigation_count,
            "default_spacecraft": len(first),
            "visible_name_flag_labels": label_count,
            "name_before_flag": True,
            "country_hover": True,
            "hover_highlights_trajectory": True,
            "iss_movement_verified": True,
            "trajectory_cache_verified": True,
            "scope_and_track_controls": True,
            "historical_playback_clears_tracks": True,
            "server_lifecycle_actions": 0,
            "errors": errors,
        }
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
