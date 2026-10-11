"""Check map feedback and military navigation against the existing servers only."""

import argparse
import json
import math
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", required=True)
    args = parser.parse_args()
    output = Path("data/run/map-ux")
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=args.chromium,
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_extra_http_headers(
            {"X-Forwarded-For": "2001:db8:" + ":".join(uuid4().hex[i : i + 4] for i in range(0, 24, 4))}
        )
        page.add_init_script("""sessionStorage.setItem('osint.layers',JSON.stringify(['geopolitical','military']));sessionStorage.setItem('osint.analysisOverlays','false');
            const realFetch = window.fetch.bind(window);
            window.fetch = async (...args) => {
                const response = await realFetch(...args);
                if(window.testSlowRefresh && /\\/api\\/(status|timeline)/.test(String(args[0])))
                    await new Promise(resolve => setTimeout(resolve,6000));
                if(window.testSlowDetail && String(args[0]).includes('/api/events/'))
                    await new Promise(resolve => setTimeout(resolve,4000));
                if(window.testSlowMore && String(args[0]).includes('offset='))
                    await new Promise(resolve => setTimeout(resolve,4000));
                return response;
            };""")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:5173")

        def settled():
            page.wait_for_function(
                "document.querySelector('#refresh-time').textContent.startsWith('Read ') && !document.querySelector('#refresh').disabled && document.querySelector('#event-list').getAttribute('aria-busy')==='false'",
                timeout=45000,
            )
            expect(page.locator("#load-error")).to_be_hidden()

        settled()
        assert page.locator('[data-layer="analysis"]').count() == 0
        expect(page.locator("#reporting-signals-toggle")).to_be_visible()
        page.evaluate("window.testSlowRefresh=true")
        page.locator("#refresh").click()
        progress = page.locator("#map-progress")
        page.wait_for_timeout(1500)
        expect(page.locator("#refresh")).to_be_disabled()
        expect(progress).to_be_hidden()
        settled()
        page.locator("#period").select_option("168")
        expect(progress).to_be_visible()
        expect(progress.locator("[data-progress-title]")).to_have_text("Applying report filters")
        page.wait_for_function(
            "() => { const p=document.querySelector('#map-progress [role=progressbar]'); const n=Number(p.getAttribute('aria-valuenow')); return n>0 && n<100; }"
        )
        bounds = progress.bounding_box()
        frame = page.locator(".map-workspace").bounding_box()
        assert abs(bounds["x"] + bounds["width"] / 2 - frame["x"] - frame["width"] / 2) < 2
        assert abs(bounds["y"] + bounds["height"] / 2 - frame["y"] - frame["height"] / 2) < 2
        expect(progress.locator("[data-progress-detail]")).to_contain_text("sections checked")
        page.screenshot(path=str(output / "progress.png"))
        page.evaluate("window.testSlowRefresh=false")
        settled()
        expect(progress).to_be_hidden(timeout=45000)
        page.locator("#military-tab").click()
        expect(page.locator(".military-topic-summary").first).to_be_visible()
        first = page.locator("[data-military-topic]").first
        first.click()
        expect(first).to_have_attribute("aria-pressed", "true")
        expect(first).to_have_text("Showing on map")
        lines = json.loads(page.locator("canvas[data-ready]").get_attribute("data-military-link-sample"))
        assert lines, "No actual defence link to check"
        for line in lines:
            projected = [(x, math.log(math.tan(math.pi / 4 + y * math.pi / 360))) for x, y in line]
            a, b = projected[0], projected[-1]
            assert all(
                abs((x - a[0]) * (b[1] - a[1]) - (y - a[1]) * (b[0] - a[0])) < 1e-7 for x, y in projected
            )
        page.locator(".map-options-details > summary").click()
        page.locator("#news-connections").uncheck()
        page.locator(".map-options-details > summary").click()
        page.locator(".military-report-list").first.locator("summary").click()
        expect(page.locator(".military-report-list .brief-source").first).to_be_visible()
        page.screenshot(path="docs/military-ui-workspace.jpg", type="jpeg", quality=88)
        page.evaluate("window.testSlowDetail=true")
        page.locator(".brief-source button").first.click()
        page.wait_for_timeout(1000)
        expect(progress).to_be_hidden()
        expect(page.locator("#event-detail")).to_be_visible(timeout=15000)
        page.evaluate("window.testSlowDetail=false")
        expect(progress).to_be_hidden(timeout=15000)
        page.locator("#feed-tab").click()
        page.evaluate("window.testSlowMore=true")
        page.locator("#load-more").click()
        expect(progress).to_be_visible()
        expect(progress.locator("[data-progress-title]")).to_have_text("Loading more reports")
        assert progress.locator("[role=progressbar]").get_attribute("aria-valuenow") is None
        page.screenshot(path=str(output / "indeterminate.png"))
        expect(page.locator("#load-more")).to_be_enabled(timeout=30000)
        page.evaluate("window.testSlowMore=false")
        expect(progress).to_be_hidden()
        page.locator("#reporting-signals-toggle").focus()
        page.keyboard.press("Enter")
        settled()
        expect(page.locator("#reporting-signals-toggle")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#reporting-signals")).to_be_visible()
        page.set_viewport_size({"width": 800, "height": 900})
        expect(page.locator("#reporting-signals-toggle")).to_be_visible()
        page.screenshot(path=str(output / "narrow.png"))
        assert not errors, errors
        result = {
            "top_signals_button": True,
            "no_signals_intelligence_layer": True,
            "readable_military_topics": True,
            "active_topic_feedback": True,
            "straight_defence_links": True,
            "report_navigation": True,
            "centered_progress": True,
            "routine_refresh_has_no_progress": True,
            "opening_report_has_no_progress": True,
            "real_section_progress": True,
            "indeterminate_operation_feedback": True,
            "progress_clears_after_completion": True,
            "keyboard_signals": True,
            "narrow_layout": True,
            "server_lifecycle_actions": 0,
            "errors": errors,
        }
        Path("docs/map-ux-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
