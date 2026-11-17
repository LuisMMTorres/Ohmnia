const { chromium } = require("playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  try {
    await page.goto((process.env.BASE || "http://127.0.0.1:8766") + "/#simulator");
    await page.waitForSelector(".schematic-canvas");
    page.on("dialog", (d) => d.accept());
    await page.getByRole("button", { name: "Novo", exact: true }).click();
    await page
      .getByRole("combobox", { name: "Adicionar instrumento", exact: true })
      .selectOption("supply");
    const picker = page.getByRole("combobox", { name: "Selecionar componente", exact: true });
    assert.equal(await page.locator(".netlabel").count(), 6);
    await picker.selectOption("PS1-2");
    await page.locator(".properties").getByRole("button", { name: "Apagar", exact: true }).click();
    assert.equal(await page.locator(".netlabel").count(), 4);
    assert.equal(await page.locator(".netlabel").filter({ hasText: "PS1_ch2" }).count(), 0);
    for (const channel of [1, 3]) {
      await picker.selectOption(`PS1-${channel}`);
      await page
        .locator(".schematic-editor")
        .getByRole("button", { name: "Enquadrar", exact: true })
        .focus();
      await page.keyboard.press("Delete");
      await page.waitForFunction(
        (id) =>
          !JSON.parse(localStorage.getItem("circuitos.schematic")).components.some(
            (c) => c.id === id,
          ),
        `PS1-${channel}`,
      );
    }
    assert.equal(await page.locator(".netlabel").count(), 0);
    const clean = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("circuitos.schematic")),
    );
    assert.deepEqual(clean.probes, []);
    assert.deepEqual(clean.breadboard.parts, []);
    await page.evaluate(
      (sch) =>
        localStorage.setItem(
          "circuitos.schematic",
          JSON.stringify({
            ...sch,
            labels: [
              { id: "PS9-p1", name: "PS9_ch1", x: 0, y: 0 },
              { id: "PS9-n1", name: "0", x: 0, y: 4 },
              { id: "manual", name: "out", x: 10, y: 0 },
            ],
          }),
        ),
      clean,
    );
    await page.reload();
    await page.waitForSelector(".schematic-canvas");
    assert.deepEqual(await page.locator(".netlabel text").allTextContents(), ["out"]);
    console.log("Schematic source deletion E2E: ok");
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
