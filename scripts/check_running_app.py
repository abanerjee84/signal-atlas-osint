"""webapp-testing reconnaissance against an existing app; no server lifecycle actions.

Install the optional Python Playwright tool before running this script. It can use
an already installed Chromium binary via --chromium. Does not invoke browser install,
START.bat, npm dev/preview, uvicorn, or any server helper.
"""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--output", default="data/run/public-update-browser")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=args.chromium,
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        def isolate_test_peer():
            # Local test proxy identity, as used by tests/browser/dashboard.spec.js.
            # Production Nginx overwrites this header; application limits remain intact.
            value = uuid4().hex[:24]
            page.set_extra_http_headers(
                {"X-Forwarded-For": "2001:db8:" + ":".join(value[i : i + 4] for i in range(0, 24, 4))}
            )

        isolate_test_peer()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def settled():
            # Live telemetry keeps making requests. Check one atomic ready
            # state, rather than racing two assertions against the next poll.
            page.wait_for_function(
                "document.querySelector('#refresh-time').textContent.startsWith('Read ') && "
                "!document.querySelector('#refresh').disabled && "
                "document.querySelector('#event-list').getAttribute('aria-busy') === 'false'",
                timeout=45000,
            )
            expect(page.locator("#load-error")).to_be_hidden()

        page.goto(args.url)
        settled()
        page.wait_for_selector('canvas[data-ready="true"]', timeout=30000)
        page.get_by_label("Cyber: Threat Actors", exact=False).wait_for()
        page.screenshot(path=str(output / "world.png"), full_page=False)
        initial = {
            "layers": page.locator("input[data-layer]").count(),
            "threat_cards": page.locator(".event-button").filter(has_text="Threat Actor").count(),
            "threat_edges": page.locator('canvas[data-ready="true"]').get_attribute(
                "data-threat-connections"
            ),
        }
        page.locator('input[data-layer="cyber"]').uncheck()
        settled()
        expect(page.locator('[data-country-rank="cyber"]')).to_be_hidden()
        expect(page.locator('canvas[data-ready="true"]')).to_have_attribute("data-threat-directions", "0")
        expect(page.locator('canvas[data-ready="true"]')).to_have_attribute("data-threat-endpoints", "0")
        assert page.locator('input[data-layer="cyber"]').is_checked() is False
        expect(page.locator('canvas[data-ready="true"]')).to_have_attribute("data-threat-connections", "0")
        assert page.locator(".event-button").filter(has_text="Threat Actor").count() == 0
        page.locator('input[data-layer="cyber"]').check()
        settled()
        page.locator('input[data-layer="sentiment"]').check()
        page.locator("#sentiment-kind").select_option("public")
        settled()
        page.locator("#social-posts-section").wait_for(state="visible")
        page.screenshot(path=str(output / "sentiment.png"), full_page=False)
        summary = {
            "url": args.url,
            "server_lifecycle_actions": 0,
            "initial": initial,
            "social_posts": page.locator("#social-posts article.social-post").count(),
            "errors": errors,
        }
        assert initial["layers"] == 9
        assert summary["social_posts"] > 0, "No real public-discussion records displayed"
        page.locator("#social-posts article.social-post").first.scroll_into_view_if_needed()
        page.screenshot(path=str(output / "posts.png"), full_page=False)
        # Isolate the threat layer, checking real retained reports and detail evidence.
        # Reload a persisted single-layer selection in one step rather than
        # issuing an entire dashboard query for every unchecked layer.
        page.evaluate("sessionStorage.setItem('osint.layers', JSON.stringify(['threat']))")
        isolate_test_peer()
        page.reload()
        settled()
        page.locator("#period").select_option("168")
        page.get_by_role("button", name="Events", exact=True).click()
        settled()
        cards = page.locator(".event-button").filter(has_text="Threat Actor")
        assert cards.count() > 0, "No real threat reports in the last seven days"
        assert page.locator(".event-button").count() == cards.count(), "Disabled layers leaked into the feed"
        if page.locator("#country-ribbon-body").is_hidden():
            page.locator("#country-ribbon-toggle").click()
        page.locator('[data-country-rank="cyber"]').click()
        page.locator("#cyber-route-source").select_option("bunkerweb_threatmap")
        routes = page.locator("[data-threat-route]")
        assert routes.count() > 0, "No country-pair detections in Countries sidebar"
        expect(page.locator("#cyber-route-headings")).to_be_visible()
        canvas = page.locator('canvas[data-ready="true"]')
        page.wait_for_function(
            "Number(document.querySelector('canvas[data-ready]').dataset.threatDirections) > 0 && Number(document.querySelector('canvas[data-ready]').dataset.threatEndpoints) > 0"
        )
        summary["cyber_country_routes"] = routes.count()
        summary["direction_arrows"] = canvas.get_attribute("data-threat-directions")
        summary["country_endpoints"] = canvas.get_attribute("data-threat-endpoints")
        expect(page.locator("#cyber-map-legend")).to_be_visible()
        position = canvas.get_attribute("data-threat-arrow-position")
        page.wait_for_timeout(400)
        assert position != canvas.get_attribute("data-threat-arrow-position"), "Direction arrows stayed still"
        summary["animated_arrows"] = True
        page.emulate_media(reduced_motion="reduce")
        page.wait_for_timeout(250)
        stopped_position = canvas.get_attribute("data-threat-arrow-position")
        page.wait_for_timeout(400)
        assert stopped_position == canvas.get_attribute("data-threat-arrow-position")
        page.emulate_media(reduced_motion="no-preference")
        page.wait_for_timeout(400)
        assert stopped_position != canvas.get_attribute("data-threat-arrow-position")
        summary["reduced_motion_respected"] = True
        hover_point = json.loads(canvas.get_attribute("data-threat-hover-point"))
        assert hover_point, "No visible cyber endpoint to test hover"
        bounds = canvas.bounding_box()
        page.mouse.move(bounds["x"] + hover_point[0], bounds["y"] + hover_point[1])
        expect(page.locator(".map-hover-details")).to_be_visible()
        expect(page.locator(".map-hover-details")).to_contain_text("Country-level evidence")
        expect(page.locator(".map-hover-details")).to_contain_text("Vector / type:")
        page.screenshot(path=str(output / "hover-evidence.png"), full_page=False)
        page.mouse.move(10, 10)
        expect(page.locator(".map-hover-details")).to_have_count(0)
        page.screenshot(path=str(output / "country-routes.png"), full_page=False)
        routes.first.click()
        page.wait_for_timeout(800)
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("A · Attacker / origin")
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("V · Victim / target")
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("Vector / type:")
        page.screenshot(path=str(output / "selected-route.png"), full_page=False)
        page.locator("#threat-map-references").locator("summary").click()
        page.screenshot(path=str(output / "threats.png"), full_page=False)
        traffic = cards.filter(has_text="BunkerWeb WAF:")
        assert traffic.count() > 0, "No real provider traffic samples displayed"
        traffic.first.click()
        page.locator("#event-detail").wait_for(state="visible")
        assert "Attribution evidence" in page.locator("#event-detail").inner_text()
        assert "Traffic origin country" in page.locator("#event-detail").inner_text()
        assert "Unknown; receipt time used in timeline" in page.locator("#event-detail").inner_text()
        assert "Named actor\nUnknown actor" in page.locator("#event-detail").inner_text()
        assert "Bitdefender" in page.locator("#threat-stream-health").inner_text()
        assert page.locator("#event-detail a[target='_blank']").count() > 0
        page.screenshot(path=str(output / "threat-detail.png"), full_page=False)
        summary["threat_seven_day_cards"] = cards.count()
        summary["bunkerweb_cards"] = traffic.count()
        summary["threat_seven_day_edges"] = page.locator('canvas[data-ready="true"]').get_attribute(
            "data-threat-connections"
        )
        assert not errors
        (output / "result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        browser.close()
        if errors:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
