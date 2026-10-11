"""Verify the map layout and provider vectors on the already running dashboard."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--output", default="data/run/map-layout-browser")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    checks = []
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
        canvas = page.locator('canvas[data-ready="true"]')

        def verify_frame(label):
            page.locator("#reset-view").click()
            page.wait_for_timeout(500)
            bounds = canvas.bounding_box()
            ribbon = page.locator("#country-ribbon").bounding_box()
            toolbar = page.locator(".map-toolbar").bounding_box()
            assert bounds["x"] >= ribbon["x"] + ribbon["width"] - 1, label
            assert bounds["y"] >= toolbar["y"] + toolbar["height"] - 1, label
            frame = json.loads(canvas.get_attribute("data-world-frame"))
            assert all(0 <= x <= bounds["width"] and 0 <= y <= bounds["height"] for x, y in frame), (
                label,
                frame,
                bounds,
            )
            checks.append(
                {
                    "view": label,
                    "toolbar_height": toolbar["height"],
                    "map_width": bounds["width"],
                    "map_height": bounds["height"],
                }
            )
            return bounds["width"]

        expanded = verify_frame("desktop expanded")
        assert page.locator(".map-toolbar").bounding_box()["height"] <= 90
        page.locator("#country-ribbon-toggle").click()
        collapsed = verify_frame("desktop collapsed")
        assert collapsed > expanded + 200
        page.locator("#country-ribbon-toggle").click()
        verify_frame("desktop restored")
        options = page.locator(".map-options-details")
        options.locator("summary").focus()
        page.keyboard.press("Enter")
        expect(options).to_have_attribute("open", "")
        expect(page.locator("#heatmap")).to_be_visible()
        page.locator("#heatmap").check()
        page.locator("#heatmap").uncheck()
        page.keyboard.press("Escape")
        expect(page.locator("#heatmap")).to_be_hidden()
        page.locator(".map-legend-details summary").click()
        expect(page.locator(".map-legend-body")).to_be_visible()
        page.keyboard.press("Escape")
        page.locator("#cyber-route-source").select_option("imperva_threatmap")
        routes = page.locator("[data-threat-route]")
        assert routes.count() > 0
        expect(routes.first.locator(".route-vector")).to_be_visible()
        assert "Not specified" not in routes.first.locator(".route-vector").inner_text()
        routes.first.click()
        page.wait_for_timeout(800)
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("Vector / type:")
        expect(canvas).to_have_attribute("data-world-view", "false")
        page.locator("#country-ribbon-toggle").click()
        page.wait_for_timeout(500)
        expect(canvas).to_have_attribute("data-world-view", "false")
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("Vector / type:")
        page.locator("#country-ribbon-toggle").click()
        verify_frame("selected route reset")
        bounds = canvas.bounding_box()
        page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        page.mouse.down()
        page.mouse.move(bounds["x"] + bounds["width"] / 2 + 60, bounds["y"] + bounds["height"] / 2, steps=8)
        page.mouse.up()
        expect(canvas).to_have_attribute("data-world-view", "false")
        page.locator("#country-ribbon-toggle").click()
        page.wait_for_timeout(500)
        expect(canvas).to_have_attribute("data-world-view", "false")
        page.locator("#country-ribbon-toggle").click()
        verify_frame("manual view reset")
        page.screenshot(path=str(output / "desktop.png"))
        page.screenshot(path="docs/threat-actor-workspace.jpg", type="jpeg", quality=88)
        page.locator("#cyber-route-source").select_option("bitdefender_threatmap")
        assert routes.count() > 0
        expect(routes.first.locator(".route-vector")).to_contain_text("Not specified by provider")
        routes.first.click()
        expect(page.locator(".maplibregl-popup-content")).to_contain_text(
            "Vector / type: Not specified by provider"
        )
        for width, height in [(1600, 1000), (1280, 900), (800, 900)]:
            page.set_viewport_size({"width": width, "height": height})
            if width == 800 and page.locator("#country-ribbon-body").is_visible():
                page.locator("#country-ribbon-toggle").click()
            verify_frame(f"{width}x{height}")
            page.screenshot(path=str(output / f"layout-{width}.png"))
        expect(page.locator("#load-error")).to_be_hidden()
        assert not errors, errors
        result = {
            "layout_checks": checks,
            "provider_vectors": True,
            "unknown_vector_label": True,
            "keyboard_menus": True,
            "selected_route_preserved": True,
            "manual_view_preserved": True,
            "errors": errors,
            "server_lifecycle_actions": 0,
        }
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
