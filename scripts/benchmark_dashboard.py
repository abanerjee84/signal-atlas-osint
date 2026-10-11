"""Measure the existing dashboard only. Never starts or stops a server."""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--output", default="data/run/performance-before.json")
    parser.add_argument("--max-refresh-seconds", type=float)
    parser.add_argument("--require-card-reuse", action="store_true")
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=args.chromium,
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        peer = uuid4().hex[:24]
        page.set_extra_http_headers(
            {"X-Forwarded-For": "2001:db8:" + ":".join(peer[i : i + 4] for i in range(0, 24, 4))}
        )
        page.add_init_script("""window.benchmarkLongTasks=[];
            new PerformanceObserver(list=>window.benchmarkLongTasks.push(...list.getEntries().map(e=>({start:e.startTime,duration:e.duration})))).observe({type:'longtask',buffered:true});""")
        timings = []
        errors = []
        started = {}
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: (
                started.update({request: time.perf_counter()}) if "/api/" in request.url else None
            ),
        )

        def finished(request):
            if request in started:
                timings.append(
                    {
                        "endpoint": request.url.split("/api/", 1)[1].split("?", 1)[0],
                        "seconds": round(time.perf_counter() - started.pop(request), 3),
                    }
                )

        page.on("requestfinished", finished)
        page.on("requestfailed", finished)
        start = time.perf_counter()
        page.goto("http://127.0.0.1:5173")
        page.wait_for_function(
            "document.querySelector('#refresh-time').textContent.startsWith('Read ') && !document.querySelector('#refresh').disabled",
            timeout=90000,
        )
        initial = round(time.perf_counter() - start, 3)
        page.evaluate("""() => {
            const button=[...document.querySelectorAll('#event-list .event-button')].find(b=>!b.classList.contains('orbital-card') && !b.innerText.includes('Aviation'));
            window.benchmarkCard=button;
            window.benchmarkRow=button?.closest('li');
            button?.focus();
        }""")
        print(json.dumps({"initial_ready_seconds": initial, "requests": timings}), flush=True)
        baseline_requests = len(timings)
        start = time.perf_counter()
        page.evaluate("document.querySelector('#refresh').click()")
        page.wait_for_function(
            "!document.querySelector('#refresh').disabled && document.querySelector('#event-list').getAttribute('aria-busy')==='false'",
            timeout=90000,
        )
        refresh = round(time.perf_counter() - start, 3)
        reused = page.evaluate(
            "window.benchmarkRow?.isConnected && window.benchmarkCard===document.activeElement"
        )
        result = {
            "initial_ready_seconds": initial,
            "refresh_ready_seconds": refresh,
            "initial_request_count": baseline_requests,
            "requests": timings,
            "long_tasks": page.evaluate("window.benchmarkLongTasks"),
            "errors": errors,
            "server_lifecycle_actions": 0,
            "unchanged_card_and_focus_retained": reused,
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
        assert not errors, errors
        if args.require_card_reuse:
            assert reused, "An unchanged feed card lost its node or keyboard focus"
        if args.max_refresh_seconds:
            assert refresh <= args.max_refresh_seconds, "Dashboard refresh exceeded its performance budget"
        browser.close()


if __name__ == "__main__":
    main()
