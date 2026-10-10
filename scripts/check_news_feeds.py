"""Read-only validation of candidate public publisher feeds."""

import asyncio
import json
import ssl

import httpx

from backend.feeds import parse_feed

URLS = [
    "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6311",
    "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6511",
    "https://en.mercopress.com/rss",
    "https://www.africanews.com/feed/rss",
    "https://www.rfi.fr/en/rss",
    "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
    "https://buenosairesherald.com/feed",
    "https://www.abc.net.au/news/feed/51120/rss.xml",
    "https://www.euronews.com/rss?level=theme&name=news",
    "https://www.theguardian.com/world/africa/rss",
    "https://www.theguardian.com/world/americas/rss",
    "https://www.theguardian.com/world/asia/rss",
]


async def main():
    semaphore = asyncio.Semaphore(3)
    async with httpx.AsyncClient(
        timeout=25, verify=ssl.create_default_context(), follow_redirects=False
    ) as client:

        async def check(url):
            async with semaphore:
                try:
                    response = await client.get(url)
                    records = parse_feed(response.content) if response.is_success else []
                    result = {
                        "url": url,
                        "status": response.status_code,
                        "items": len(records),
                        "first_title": records[0].get("title") if records else None,
                        "redirect": response.headers.get("location"),
                    }
                except Exception as error:
                    result = {"url": url, "error": type(error).__name__}
                print(json.dumps(result, ensure_ascii=False))

        await asyncio.gather(*(check(url) for url in URLS))


if __name__ == "__main__":
    asyncio.run(main())
