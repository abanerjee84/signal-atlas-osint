"""Test conflict symbols, hover summaries and reporting signals on the existing app only."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--chromium", required=True)
    args = parser.parse_args()
    output = Path("data/run/conflict-workspace")
    output.mkdir(parents=True, exist_ok=True)
    errors = []
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
            "sessionStorage.setItem('osint.layers',JSON.stringify(['geopolitical','military']));sessionStorage.setItem('osint.analysisOverlays','false')"
        )
        page.on("pageerror", lambda error: errors.append(str(error)))

        def settled():
            page.wait_for_function(
                "document.querySelector('#refresh-time').textContent.startsWith('Read ') && "
                "!document.querySelector('#refresh').disabled && "
                "document.querySelector('#event-list').getAttribute('aria-busy') === 'false'",
                timeout=45000,
            )
            expect(page.locator("#load-error")).to_be_hidden()

        page.goto(args.url)
        settled()
        canvas = page.locator('canvas[data-ready="true"]')
        canvas.wait_for(timeout=30000)
        expect(page.locator('[data-count="military"]')).not_to_have_text("0")
        expect(page.locator('[data-count="geopolitical"]')).not_to_have_text("0")
        page.screenshot(path=str(output / "initial.png"))
        military_card = (
            page.locator(".event-button")
            .filter(has_text="Military OSINT")
            .filter(has_text="CONFLICT_LIVEUAMAP")
            .first
        )
        expect(military_card).to_be_visible()
        title = military_card.locator(".event-title").inner_text()
        target_id = military_card.get_attribute("data-event-id")
        page.locator("#search").fill(title[:160])
        page.locator("#search-form button").click()
        settled()
        expect(canvas).not_to_have_attribute("data-conflict-hover-points", "[]")
        page.wait_for_function(
            "id => JSON.parse(document.querySelector('canvas[data-ready]').dataset.conflictHoverPoints || '[]').some(p => p.event_id === id && p.type && p.category === 'military')",
            arg=target_id,
        )
        points = json.loads(canvas.get_attribute("data-conflict-hover-points"))
        page.screenshot(path=str(output / "focused.png"))
        bounds = canvas.bounding_box()
        point = next(
            p
            for p in points
            if p.get("type")
            and p.get("category") == "military"
            and 20 < p["x"] < bounds["width"] - 30
            and 20 < p["y"] < bounds["height"] - 30
        )
        page.mouse.move(bounds["x"] + point["x"], bounds["y"] + point["y"])
        expect(page.locator(".map-hover-details")).to_be_visible()
        expect(page.locator(".map-hover-details .hover-summary").first).to_be_visible()
        expect(page.locator(".map-hover-details .hover-kind")).to_be_visible()
        assert len(page.locator(".map-hover-details").inner_text()) > 60
        page.screenshot(path=str(output / "hover.png"))
        page.mouse.move(20, 20)
        page.locator("#search").fill("")
        page.locator("#search-form button").click()
        settled()
        page.locator("#conflict-legend summary").click()
        assert page.locator(".conflict-key-item").count() == 14
        expect(page.locator("#conflict-symbol-key")).to_contain_text("Siren")
        page.locator("#conflict-legend summary").click()
        page.locator("#feed-tab").click()
        cards = page.locator(".event-button").filter(has_text="CONFLICT_LIVEUAMAP")
        assert cards.count() > 0, "No real Liveuamap reports reached the current feed"
        cards.first.click()
        expect(page.locator("#event-detail")).to_contain_text("Cited original source")
        expect(page.locator("#event-detail")).to_contain_text("approximate")
        expect(canvas).not_to_have_attribute("data-conflict-kinds", "")
        conflict_kinds = canvas.get_attribute("data-conflict-kinds")
        page.screenshot(path=str(output / "conflict-icons.png"))
        page.locator("#event-detail .detail-close").click()
        page.locator("#reset-view").click()
        page.locator('[data-layer="analysis"]').check()
        settled()
        expect(page.locator("#reporting-signals")).to_be_visible()
        expect(page.locator("#analysis-view")).to_be_hidden()
        expect(page.locator("#analysis-overlays")).to_be_checked()
        expect(page.locator("#anomaly-alerts")).not_to_be_empty()
        before = page.locator("#anomaly-alerts").inner_text()
        page.locator("#refresh").click()
        settled()
        expect(page.locator("#anomaly-alerts")).not_to_be_empty()
        page.screenshot(path="docs/conflict-workspace.jpg", type="jpeg", quality=88)
        signals = page.locator('[data-count="analysis"]').inner_text()
        page.locator(".map-options-details summary").click()
        page.locator("#analysis-overlays").uncheck()
        settled()
        expect(page.locator('[data-layer="analysis"]')).not_to_be_checked()
        expect(page.locator("#analysis-evidence")).to_be_hidden()
        expect(page.locator("#reporting-signals")).to_be_hidden()
        page.keyboard.press("Escape")
        page.locator('[data-layer="military"]').check()
        page.locator("#military-tab").click()
        expect(page.locator("#military-groups .military-brief").first).to_be_visible()
        expect(page.locator("#military-summary")).to_contain_text("media reports")
        page.locator("#feed-tab").click()
        page.set_viewport_size({"width": 800, "height": 900})
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        # Drive the real handlers together; cancellation alone still launches
        # duplicate API work unless the request batch itself is coalesced.
        batches = []
        page.on("request", lambda request: batches.append(1) if "/api/status" in request.url else None)
        page.evaluate("""() => {
            const layer = document.querySelector('[data-layer="sentiment"]');
            layer.checked = true;
            layer.dispatchEvent(new Event('change'));
            const kind = document.querySelector('#sentiment-kind');
            kind.value = 'public';
            kind.dispatchEvent(new Event('change'));
        }""")
        settled()
        assert len(batches) == 1, "Adjacent filters dispatched duplicate query batches"
        expect(page.locator("#social-posts article.social-post").first).to_be_visible()
        assert not errors, errors
        result = {
            "military_count": page.locator('[data-count="military"]').inner_text(),
            "geopolitical_count": page.locator('[data-count="geopolitical"]').inner_text(),
            "visible_conflict_types": conflict_kinds,
            "hover_summary": True,
            "liveuamap_original_sources": True,
            "reporting_signals": signals,
            "alerts_survive_refresh": bool(before),
            "one_signal_switch": True,
            "adjacent_filter_batches": len(batches),
            "server_lifecycle_actions": 0,
            "errors": errors,
        }
        Path("docs/conflict-ui-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
