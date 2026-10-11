"""Optional normal browser rendering for public threat-map tables, no server."""

import asyncio
import re

from backend.connectors.base import ProviderError


class ThreatTableReader:
    def __init__(self, chromium=None):
        self.chromium = chromium
        self.runtime = self.browser = self.page = None
        self.imperva_page = None
        self.imperva_sample = None
        self.imperva_ready = asyncio.Event()
        self.imperva_loaded_at = 0
        self.start_lock = asyncio.Lock()

    async def start(self):
        async with self.start_lock:
            if self.browser is None:
                from playwright.async_api import async_playwright

                self.runtime = await async_playwright().start()
                self.browser = await self.runtime.chromium.launch(
                    headless=True, executable_path=self.chromium
                )

    async def rows(self, homepage):
        try:
            if self.page is None or self.page.is_closed():
                await self.start()
                self.page = await self.browser.new_page(timezone_id="UTC")
                await self.page.goto(homepage, wait_until="domcontentloaded", timeout=15000)
                await self.page.locator("#attacks_data").wait_for(timeout=10000)
            return await self.page.locator("#attacks_data tr").evaluate_all(
                "rows => rows.slice(0,500).map(r => [...r.querySelectorAll('td')].map(c => c.textContent.trim())).filter(r => r[2]?.toUpperCase() === 'ATTACK')"
            )
        except Exception as error:
            if self.page:
                await self.page.close()
                self.page = None
            raise ProviderError(
                "Bitdefender rendered ATTACK table unavailable (" + type(error).__name__ + ")", retry_after=60
            ) from None

    async def imperva_dataset(self):
        # Observe only the public CSV response the site's own table loads.
        # No injected fetch, cookie copying, fabricated user-agent or challenge bypass.
        async def delivered(response):
            match = re.fullmatch(
                r"https://www\.imperva\.com/public/threat-map-data-v2/day=(\d{4}-\d{2}-\d{2})/data/(\d{1,2})\.gz",
                response.url,
            )
            if match and response.status == 200:
                body = await response.body()
                if len(body) <= 1_048_576 and body[:2] == b"\x1f\x8b":
                    self.imperva_sample = (body, match[1], int(match[2]))
                    self.imperva_ready.set()

        try:
            await self.start()
            if self.imperva_page is None or self.imperva_page.is_closed():
                self.imperva_page = await self.browser.new_page(timezone_id="UTC")
                self.imperva_page.on("response", delivered)
                await self.imperva_page.goto(
                    "https://www.imperva.com/cyber-threat-attack-map/",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                self.imperva_loaded_at = asyncio.get_running_loop().time()
            elif asyncio.get_running_loop().time() - self.imperva_loaded_at >= 900:
                self.imperva_sample = None
                self.imperva_ready.clear()
                await self.imperva_page.reload(wait_until="domcontentloaded", timeout=15000)
                self.imperva_loaded_at = asyncio.get_running_loop().time()
            if self.imperva_sample is None:
                await asyncio.wait_for(self.imperva_ready.wait(), timeout=20)
            return self.imperva_sample
        except asyncio.CancelledError:
            if self.imperva_page:
                await self.imperva_page.close()
            self.imperva_page = None
            self.imperva_sample = None
            self.imperva_ready.clear()
            raise
        except Exception as error:
            if self.imperva_page:
                await self.imperva_page.close()
            self.imperva_page = None
            self.imperva_sample = None
            self.imperva_ready.clear()
            raise ProviderError(
                "Imperva public page did not deliver a usable dataset ("
                + type(error).__name__
                + "); collection remains blocked",
                retry_after=900,
            ) from None

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.runtime:
            await self.runtime.stop()
        self.runtime = self.browser = self.page = None
        self.imperva_page = self.imperva_sample = None
