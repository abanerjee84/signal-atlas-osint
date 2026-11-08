export async function openLayerTopic(page, topic) {
  const group = page.locator(`[data-layer-topic="${topic}"]`);
  await group.waitFor({ state: "attached" });
  if (!(await group.evaluate((node) => node.open)))
    await group.locator(":scope > summary").click();
}
