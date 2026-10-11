"""Visually check military symbols against the existing dashboard; starts no server."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", required=True)
    args = parser.parse_args()
    output = Path("data/run/military-icons")
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=args.chromium,
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1920, "height": 900})
        page.set_extra_http_headers(
            {"X-Forwarded-For": "2001:db8:" + ":".join(uuid4().hex[i:i+4] for i in range(0, 24, 4))}
        )
        page.add_init_script(
            "sessionStorage.setItem('osint.layers',JSON.stringify(['military']));"
            "sessionStorage.setItem('osint.analysisOverlays','false');"
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" and "layers." in message.text else None)
        # Expose the real map in this test browser only, for rendered badge checks.
        def expose_map(route):
            response = route.fetch()
            content = response.text().replace(
                "worldMap = createWorldMap(state.world, {",
                "worldMap = window.testMilitaryWorkspace = createWorldMap(state.world, {",
                1,
            )
            route.fulfill(response=response, body=content)

        page.route("**/src/main.js*", expose_map)
        page.goto("http://127.0.0.1:5173")

        def settled():
            page.wait_for_function(
                "document.querySelector('#refresh-time').textContent.startsWith('Read ') && "
                "!document.querySelector('#refresh').disabled && "
                "document.querySelector('#event-list').getAttribute('aria-busy')==='false'",
                timeout=45000,
            )
            expect(page.locator("#load-error")).to_be_hidden()

        settled()
        page.locator("#period").select_option("168")
        settled()
        canvas = page.locator('canvas[data-ready="true"]')
        canvas.wait_for(timeout=30000)
        page.locator("#reset-view").click()
        expect(page.locator('[data-count="military"]')).not_to_have_text("0")
        page.locator("#conflict-legend summary").click()
        expect(page.locator(".conflict-key-item")).to_have_count(14)
        expect(page.locator("#military-symbol-colors")).to_be_visible()
        page.wait_for_function("window.testMilitaryWorkspace?.map.queryRenderedFeatures({layers:['military-context']}).some(f=>f.properties.count>1)")
        aggregates = page.evaluate("""() => {
            const map = window.testMilitaryWorkspace.map;
            return map.queryRenderedFeatures({layers:['military-context']})
                .filter(f=>f.properties.count>1)
                .map(f=>({country:f.properties.code,reports:f.properties.count,
                    badgeLoaded:map.hasImage('military-brief-'+(f.properties.count>99?'99plus':f.properties.count))}));
        }""")
        assert aggregates and all(item["badgeLoaded"] for item in aggregates), aggregates
        page.screenshot(path="docs/military-icons-workspace.jpg", type="jpeg", quality=90)
        page.locator("#conflict-symbol-key").screenshot(path=str(output / "key.png"))
        military_count = page.locator('[data-count="military"]').inner_text()
        cards = page.locator(".event-button").filter(has_text="CONFLICT_LIVEUAMAP")
        assert cards.count(), "No real located conflict report available to inspect"
        card = cards.first
        card.scroll_into_view_if_needed()
        title = card.locator(".event-title").text_content().strip()
        assert title, "Stored source headline is required"
        event_id = card.get_attribute("data-event-id")
        page.locator("#search").fill(title[:160])
        page.locator("#search-form button").click()
        settled()
        page.screenshot(path=str(output / "focused.png"))
        page.wait_for_function(
            "id => JSON.parse(document.querySelector('canvas[data-ready]').dataset.conflictHoverPoints || '[]').some(p=>p.event_id===id && p.type)",
            arg=event_id,
        )
        bounds = canvas.bounding_box()
        points = json.loads(canvas.get_attribute("data-conflict-hover-points"))
        point = next(p for p in points if p.get("event_id") == event_id)
        page.mouse.move(bounds["x"] + point["x"], bounds["y"] + point["y"])
        expect(page.locator(".map-hover-details .hover-summary").first).to_be_visible()
        expect(page.locator(".map-hover-details .hover-kind")).to_be_visible()
        page.screenshot(path=str(output / "hover.png"))
        hover = page.locator(".map-hover-details").inner_text()
        assert len(hover) > 60
        page.mouse.move(20, 20)
        # Key matches geopolitical rendering when that is the only enabled layer.
        page.locator('[data-layer="geopolitical"]').check()
        page.locator('[data-layer="military"]').uncheck()
        settled()
        expect(page.locator("#military-symbol-colors")).to_be_hidden()
        assert not errors, errors
        result = {
            "military_count": military_count,
            "real_report_hover": True,
            "report_topic": point["type"],
            "legend_switches_with_layer": True,
            "visible_report_count_badges": len(aggregates),
            "maximum_edge_opacity": page.evaluate("window.testMilitaryWorkspace.map.getPaintProperty('military-connections','line-opacity').at(-1)"),
            "server_lifecycle_actions": 0,
            "errors": errors,
        }
        Path("docs/military-icons-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
