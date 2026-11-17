const { chromium } = require("playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  try {
    await page.goto((process.env.BASE || "http://127.0.0.1:8766") + "/#simulator");
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.reload();
    await page.waitForSelector(".schematic-canvas");
    await page.getByRole("button", { name: "Protoboard", exact: true }).click();
    const mounted = page.waitForResponse(
      (r) => r.url().endsWith("/breadboard/auto") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Montar automaticamente", exact: true }).click();
    assert.equal((await (await mounted).json()).report.ok, true);
    await page.getByRole("button", { name: "Simular", exact: true }).click();
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll(".simulation-output b")].some(
          (el) => el.textContent === "Concluída",
        ),
      undefined,
      { timeout: 120000 },
    );
    assert.equal(await page.locator(".bb-side").isVisible(), false);
    assert.equal(await page.locator(".bb-info").isVisible(), false);
    const board = await page.locator(".bb-canvas").boundingBox();
    const results = await page.locator(".simulation-output").boundingBox();
    assert.ok(board.width > 800, "board keeps useful space beside the results");
    assert.ok(results.x >= board.x + board.width, "results do not overlap the board");
    if (process.env.SHOTS) {
      await page.locator(".simulator-workbench").scrollIntoViewIfNeeded();
      await page.screenshot({
        path: process.env.SHOTS + "protoboard-results.png",
        fullPage: false,
      });
    }
    await page.setViewportSize({ width: 900, height: 900 });
    const narrowBoard = await page.locator(".bb-canvas").boundingBox();
    const narrowResults = await page.locator(".simulation-output").boundingBox();
    assert.ok(narrowBoard.width > 750);
    assert.ok(
      narrowResults.y >= narrowBoard.y + narrowBoard.height,
      "narrow screens stack the results below the board",
    );
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      true,
    );
    await page
      .getByRole("navigation", { name: "Etapas do simulador" })
      .getByRole("button", { name: /^Circuito/ })
      .click();
    assert.equal(await page.locator(".bb-side").isVisible(), true);
    assert.equal(await page.locator(".bb-info").isVisible(), true);
    console.log("Breadboard results layout E2E: ok");
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
