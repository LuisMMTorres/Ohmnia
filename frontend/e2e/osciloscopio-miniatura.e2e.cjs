const { chromium } = require("playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
  const base = process.env.BASE || "http://127.0.0.1:8766";
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const saved = () => page.evaluate(() => JSON.parse(localStorage.getItem("circuitos.schematic")));
  const connect = async (terminal, hole) => {
    await page.getByRole("button", { name: `Conectar CH1 ${terminal}`, exact: true }).click();
    await page.locator(`.bb-hole[data-hole="${hole}"]`).click({ position: { x: 1, y: 1 } });
    await page.waitForFunction(
      ([key, h]) =>
        JSON.parse(localStorage.getItem("circuitos.schematic")).bench_scope_connections["1"][
          key
        ] === h,
      [terminal === "+" ? "positive" : "negative", hole],
    );
  };
  const simulate = async () => {
    await page.getByRole("button", { name: "Simular", exact: true }).click();
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll(".simulation-output b")].some(
          (el) => el.textContent === "Concluída",
        ),
      undefined,
      { timeout: 120000 },
    );
    await page.waitForSelector('.bench-scope polyline[data-channel="1"]', { state: "attached" });
  };
  try {
    await page.goto(base + "/#simulator");
    const imported = await page.request.post(base + "/api/v1/schematic/import", {
      data: { netlist: "Miniature divider\nV1 in 0 5\nR1 in out 1k\nR2 out 0 1k\n.op\n.end" },
    });
    assert.equal(imported.ok(), true, await imported.text());
    const circuit = (await imported.json()).schematic;
    circuit.probes = [];
    await page.evaluate((c) => {
      localStorage.setItem("circuitos.schematic", JSON.stringify(c));
      sessionStorage.setItem("circuitos.simulator.view", "protoboard");
    }, circuit);
    await page.reload();
    await page.waitForSelector(".bb-layout");
    const mounted = page.waitForResponse(
      (r) => r.url().endsWith("/breadboard/auto") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Montar automaticamente", exact: true }).click();
    assert.equal((await (await mounted).json()).report.ok, true);
    await page
      .getByRole("combobox", { name: "Adicionar instrumento", exact: true })
      .selectOption("scope4");
    assert.equal(await page.locator(".scope-miniature").count(), 1);
    assert.equal(await page.locator(".scope-miniature").getByRole("button").count(), 8);
    const assembly = await saved();
    const resolved = await (
      await page.request.post(base + "/api/v1/breadboard/resolve", {
        data: { schematic: assembly },
      })
    ).json();
    const used = new Set([
      ...assembly.breadboard.parts.flatMap((p) => Object.values(p.legs)),
      ...assembly.breadboard.wires.flatMap((w) => [w.a, w.b]),
    ]);
    const conductor = (hole) => {
      const match = /^(2:)?(tp|tn|bn|bp|[a-j])(\d+)$/.exec(hole);
      return (
        (match[1] ?? "") +
        (match[2].length > 1 ? match[2] : match[3] + ("abcde".includes(match[2]) ? "L" : "R"))
      );
    };
    const spec = await (await page.request.get(base + "/api/v1/breadboard/spec")).json();
    const holes = [];
    for (const col of ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "tp", "tn", "bn", "bp"])
      for (const row of col.length === 1
        ? Array.from({ length: 63 }, (_, i) => i + 1)
        : spec.board.rail_rows)
        holes.push(col + row);
    const freeAt = (net) => {
      const occupied = assembly.breadboard.parts.flatMap((part) =>
        Object.entries(part.legs)
          .filter(([pin]) => resolved.nets[`${part.ref}:${pin}`] === net)
          .map(([, h]) => h),
      )[0];
      assert.ok(occupied, `physical node ${net} exists`);
      return holes.find((h) => !used.has(h) && conductor(h) === conductor(occupied));
    };
    const out = freeAt("out"),
      ground = freeAt("0");
    assert.ok(out && ground);
    await connect("+", out);
    assert.equal((await saved()).probes.length, 0);
    await connect("−", ground);
    assert.equal((await saved()).probes[0].name, "OSC_CH1");
    assert.equal(await page.locator(".scope-miniature .bb-lead-wire").count(), 2);
    if (process.env.SHOTS) {
      await page.locator(".scope-miniature").scrollIntoViewIfNeeded();
      await page
        .locator(".bb-canvas")
        .screenshot({ path: process.env.SHOTS + "scope-miniature-connected.png" });
    }

    await page.reload();
    await page.waitForSelector(".scope-miniature");
    assert.equal((await saved()).bench_scope_connections["1"].positive, out);
    await simulate();
    assert.match(
      await page.locator(".bench-scope").getByLabel("Leitura CH1", { exact: true }).innerText(),
      /2,5 V/,
    );
    assert.equal(
      await page
        .locator(".bench-scope")
        .getByRole("combobox", { name: "Sinal CH1", exact: true })
        .isDisabled(),
      true,
    );
    await page
      .getByRole("navigation", { name: "Etapas do simulador" })
      .getByRole("button", { name: /^Circuito/ })
      .click();
    await connect("+", ground);
    await simulate();
    assert.match(
      await page.locator(".bench-scope").getByLabel("Leitura CH1", { exact: true }).innerText(),
      /^0 V$/,
    );
    await page.getByRole("button", { name: "Desconectar CH1", exact: true }).click();
    assert.equal((await saved()).probes.length, 0);
    await page.getByRole("button", { name: "Remover osciloscópio", exact: true }).click();
    assert.equal(await page.locator(".scope-miniature").count(), 0);
    assert.deepEqual((await saved()).bench_scope_connections, {});
    assert.deepEqual(errors, []);
    console.log("Scope miniature E2E: ok (connections, persistence, 2.5 V, moved lead, removal)");
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
