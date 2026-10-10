import { chromium } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { platform, release } from "node:os";

const browser = await chromium.launch({
  headless: true,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const samples = [];
for (let index = 0; index < 5; index++) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
  });
  const page = await context.newPage();
  const session = await context.newCDPSession(page);
  await session.send("Network.enable");
  await session.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 50,
    downloadThroughput: 1250000,
    uploadThroughput: 625000,
    connectionType: "ethernet",
  });
  const began = performance.now();
  await page.goto("http://127.0.0.1:4173");
  await page.waitForFunction(
    () =>
      Number(document.querySelector("#map canvas")?.dataset.observations || 0) >
        0 && !document.querySelector("#refresh").disabled,
  );
  samples.push(Math.round(performance.now() - began));
  await context.close();
}
const result = {
  timestamp_utc: new Date().toISOString(),
  os: `${platform()} ${release()}`,
  chromium: browser.version(),
  viewport: "1440x960",
  rendering: "Headless Chromium with SwiftShader software WebGL",
  network:
    "CDP emulated 10 Mbps download, 5 Mbps upload, 50 ms latency; localhost production preview; new browser context per load",
  ready_definition:
    "Visible rendered observations and first API refresh complete",
  cold_load_samples_ms: samples,
  maximum_ms: Math.max(...samples),
  median_ms: [...samples].sort((a, b) => a - b)[2],
  limitation:
    "Five local emulated-network samples, without deployed Nginx gzip or real broadband. Does not establish actual Ubuntu serving performance or sustained GPU interaction FPS.",
};
writeFileSync(
  new URL("../docs/browser-benchmark.json", import.meta.url),
  JSON.stringify(result, null, 2),
);
console.log(JSON.stringify(result, null, 2));
await browser.close();
