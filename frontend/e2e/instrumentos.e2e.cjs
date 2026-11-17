const { chromium } = require("playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  const saved = () => page.evaluate(() => JSON.parse(localStorage.getItem("circuitos.schematic")));
  try {
    await page.goto((process.env.BASE || "http://127.0.0.1:8766") + "/#simulator");
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.reload();
    await page.waitForSelector(".schematic-canvas");
    await page.getByRole("button", { name: "Protoboard", exact: true }).click();
    const before = await saved();
    const add = page.getByRole("combobox", { name: "Adicionar instrumento", exact: true });
    await add.selectOption("supply");
    const after = await saved();
    assert.equal(after.components.length, before.components.length + 3);
    assert.equal(after.breadboard.parts.length, 3);
    assert.equal(await page.locator(".bb-instrument").count(), 3);
    const supply = page.locator(".power-supply-face").filter({ hasText: "2 canais ajustáveis" });
    await supply.getByRole("checkbox", { name: "Usar CH2 PS1", exact: true }).uncheck();
    await supply.getByRole("checkbox", { name: "Usar CH3 PS1", exact: true }).uncheck();
    assert.equal(await page.locator(".bb-instrument").count(), 1);
    assert.equal(await supply.locator(".power-channel").count(), 1);
    const channelRef = (await saved()).components.find((c) => c.params.bench_id === "PS1").ref;
    await supply
      .getByRole("combobox", { name: `Furo ${channelRef} +`, exact: true })
      .selectOption("vp1");
    await supply
      .getByRole("combobox", { name: `Furo ${channelRef} −`, exact: true })
      .selectOption("vn1");
    assert.equal((await saved()).breadboard.parts.find((p) => p.ref === channelRef).legs.p, "vp1");
    await page
      .getByRole("button", { name: `Conectar terminal ${channelRef}.n`, exact: true })
      .click();
    await page.locator('.bb-hole[data-hole="2:a12"]').click();
    await page.waitForFunction(
      (ref) =>
        JSON.parse(localStorage.getItem("circuitos.schematic")).breadboard.parts.find(
          (p) => p.ref === ref,
        ).legs.n === "2:a12",
      channelRef,
    );

    assert.equal(
      (await saved()).breadboard.parts.find((p) => p.ref === channelRef).legs.n,
      "2:a12",
    );
    await supply.getByRole("checkbox", { name: "Usar CH2 PS1", exact: true }).check();
    assert.equal(await page.locator(".bb-instrument").count(), 2);
    assert.equal((await saved()).breadboard.parts.find((p) => p.ref === channelRef).legs.p, "vp1");
    await page.getByRole("button", { name: "Remover fonte de bancada", exact: true }).click();
    const removed = await saved();
    assert.deepEqual(removed.components, before.components);
    assert.deepEqual(removed.labels, before.labels);
    assert.deepEqual(removed.probes, before.probes);
    assert.deepEqual(removed.breadboard.parts, []);
    assert.equal(await page.locator(".bb-instrument").count(), 0);
    await add.selectOption("generator");
    const generator = page.locator(".power-supply-face").filter({ hasText: /G1/ });
    assert.equal(await generator.count(), 1);
    assert.equal(await page.locator(".bb-instrument").count(), 1);
    await generator.locator("summary").click();
    await generator.getByRole("combobox", { name: "Tipo de saída", exact: true }).selectOption("i");
    assert.equal((await saved()).components.find((c) => c.ref === "G1").kind, "isin");
    await generator.getByRole("button", { name: "Remover gerador de sinais", exact: true }).click();
    assert.deepEqual((await saved()).components, before.components);
    assert.equal(await page.locator(".bb-instrument").count(), 0);
    await add.selectOption("scope2");
    assert.equal((await saved()).bench_scope_channels, 2);
    assert.equal(
      await page
        .getByRole("img", { name: "Osciloscópio aguardando aquisição", exact: true })
        .count(),
      1,
    );
    await page
      .locator(".bench-scope")
      .getByRole("combobox", { name: "Canais do instrumento", exact: true })
      .selectOption("4");
    assert.equal((await saved()).bench_scope_channels, 4);
    await page.reload();
    await page.waitForSelector(".schematic-canvas");
    await page.getByRole("button", { name: "Protoboard", exact: true }).click();
    assert.equal(
      await page
        .locator(".bench-scope")
        .getByRole("combobox", { name: "Canais do instrumento", exact: true })
        .inputValue(),
      "4",
    );
    await page.getByRole("button", { name: "Remover osciloscópio", exact: true }).click();
    assert.equal((await saved()).bench_scope_channels, 0);
    assert.equal(await page.locator(".bench-scope").count(), 0);
    assert.deepEqual(errors, []);
    console.log("Instrument add/remove E2E: ok");
  } catch (e) {
    if (process.env.SHOTS)
      await page
        .screenshot({ path: process.env.SHOTS + "instruments-failure.png", fullPage: true })
        .catch(() => {});
    throw e;
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
