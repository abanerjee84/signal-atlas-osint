"""webapp-testing reconnaissance against an existing app; no server lifecycle actions.

Install the optional Python Playwright tool before running this script. It can use
an already installed Chromium binary via --chromium. Does not invoke browser install,
START.bat, npm dev/preview, uvicorn, or any server helper.
"""

import argparse
import json
from pathlib import Path

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
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def settled():
            page.wait_for_load_state("networkidle")
            expect(page.locator("#refresh")).to_be_enabled(timeout=45000)
            expect(page.locator("#event-list")).to_have_attribute("aria-busy", "false")
            expect(page.locator("#load-error")).to_be_hidden()

        page.goto(args.url)
        settled()
        page.wait_for_selector('canvas[data-ready="true"]', timeout=30000)
        page.get_by_label("Threat Actor", exact=False).wait_for()
        page.screenshot(path=str(output / "world.png"), full_page=False)
        initial = {
            "layers": page.locator("input[data-layer]").count(),
            "threat_cards": page.locator(".event-button").filter(has_text="Threat Actor").count(),
            "threat_edges": page.locator('canvas[data-ready="true"]').get_attribute(
                "data-threat-connections"
            ),
        }
        page.locator('input[data-layer="threat"]').uncheck()
        settled()
        assert page.locator('input[data-layer="threat"]').is_checked() is False
        expect(page.locator('canvas[data-ready="true"]')).to_have_attribute("data-threat-connections", "0")
        assert page.locator(".event-button").filter(has_text="Threat Actor").count() == 0
        page.locator('input[data-layer="threat"]').check()
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
        assert initial["layers"] == 10
        assert summary["social_posts"] > 0, "No real public-discussion records displayed"
        page.locator("#social-posts article.social-post").first.scroll_into_view_if_needed()
        page.screenshot(path=str(output / "posts.png"), full_page=False)
        # Isolate the threat layer, checking real retained reports and detail evidence.
        # Reload a persisted single-layer selection in one step rather than
        # issuing an entire dashboard query for every unchecked layer.
        page.evaluate("sessionStorage.setItem('osint.layers', JSON.stringify(['threat']))")
        page.reload()
        settled()
        page.locator("#period").select_option("168")
        page.get_by_role("button", name="Events", exact=True).click()
        settled()
        cards = page.locator(".event-button").filter(has_text="Threat Actor")
        assert cards.count() > 0, "No real threat reports in the last seven days"
        assert page.locator(".event-button").count() == cards.count(), "Disabled layers leaked into the feed"
        page.locator("#threat-map-references").locator("summary").click()
        page.screenshot(path=str(output / "threats.png"), full_page=False)
        cards.first.click()
        page.locator("#event-detail").wait_for(state="visible")
        assert "Attribution evidence" in page.locator("#event-detail").inner_text()
        assert page.locator("#event-detail a[target='_blank']").count() > 0
        page.screenshot(path=str(output / "threat-detail.png"), full_page=False)
        summary["threat_seven_day_cards"] = cards.count()
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
