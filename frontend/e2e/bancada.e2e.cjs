/** Virtual bench integration. Uses the same isolated-server harness as simulador.e2e.cjs. */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const BASE = process.env.BASE || "http://127.0.0.1:8766";
const OUT = process.env.SHOTS || "";
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  const shot = async (name) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    if (OUT) await page.screenshot({ path: OUT + name, fullPage: true });
    console.log("ok", name);
  };
  const circuit = async () =>
    JSON.parse(await page.evaluate(() => localStorage.getItem("circuitos.schematic")));
  const api = async (path, body) => {
    const result = await page.request.post(BASE + "/api/v1" + path, { data: body });
    assert.equal(result.ok(), true, await result.text());
    return result.json();
  };
  try {
    await page.goto(BASE + "/#simulator");
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.reload();
    await page.waitForSelector(".schematic-canvas");
    const navigation = page.getByRole("navigation", { name: "Seções" });
    for (const name of ["Biblioteca", "Análise de dispositivos", "Análise de Projetos"])
      assert.equal(await navigation.getByRole("button", { name, exact: true }).count(), 1);
    await page.getByRole("button", { name: "Protoboard", exact: true }).click();
    assert.equal(await page.locator(".bb-board-panel").count(), 2);
    assert.equal(await page.locator(".bb-zoom select").inputValue(), "1");
    const sourceRow = page.locator(".bb-list li").filter({ hasText: /V1/ });
    await sourceRow.getByRole("button", { name: "Colocar", exact: true }).click();
    assert.equal(await page.locator(".bb-instrument").count(), 1);
    assert.equal(
      Object.keys((await circuit()).breadboard.parts.find((p) => p.ref === "V1").legs).length,
      0,
    );
    await page.getByRole("combobox", { name: "Terminal V1.p", exact: true }).selectOption("vp1");
    await page.getByRole("combobox", { name: "Terminal V1.n", exact: true }).selectOption("vn1");
    await shot("bench-01-two-boards.png");
    await page
      .getByRole("combobox", { name: "Adicionar instrumento", exact: true })
      .selectOption("supply");
    const supply = page.locator(".power-supply-face").filter({ hasText: "2 canais ajustáveis" });
    assert.equal(await supply.locator(".power-channel").count(), 3);
    for (const [i, value] of [
      [0, "12"],
      [1, "-12"],
    ]) {
      const ch = supply.locator(".power-channel").nth(i);
      await ch.locator("summary").click();
      await ch.getByRole("spinbutton", { name: /Tensão\/corrente ajustada/ }).fill(value);
    }
    const fixed = supply.locator(".power-channel").nth(2);
    await fixed.locator("summary").click();
    assert.equal(
      await fixed.getByRole("spinbutton", { name: /Tensão\/corrente ajustada/ }).isDisabled(),
      true,
    );
    assert.match(await fixed.locator("output").first().innerText(), /5 V/);
    const rRow = page.locator(".bb-list li").filter({ hasText: /R1/ });
    await rRow.getByRole("button", { name: "Colocar", exact: true }).click();
    await page.getByRole("combobox", { name: "Terminal R1.1", exact: true }).selectOption("2:a10");
    await page.getByRole("combobox", { name: "Terminal R1.2", exact: true }).selectOption("2:a14");
    const saved = await circuit();
    assert.equal(saved.breadboard.parts.find((p) => p.ref === "R1").legs["1"], "2:a10");
    const report = await api("/breadboard/check", { schematic: saved });
    assert.equal(report.ok, false); // incomplete assembly must not be reported as ready
    const probePanel = page.locator(".scope-probe-connections");
    await probePanel.getByLabel("Ponteira +").selectOption("2:b10");
    await probePanel.getByRole("button", { name: "Conectar ponteira", exact: true }).click();
    await page.waitForFunction(() =>
      JSON.parse(localStorage.getItem("circuitos.schematic")).probes.some((p) => p.name === "CH1"),
    );
    await shot("bench-02-supply.png");

    await page.getByRole("button", { name: "Esquemático 2D", exact: true }).click();
    const picker = page.getByRole("combobox", { name: "Selecionar componente", exact: true });
    await picker.selectOption(
      await picker.locator("option").filter({ hasText: /^V1 ·/ }).getAttribute("value"),
    );
    const controls = page.locator(".properties .source-controls");
    await controls.getByLabel("Forma de onda").selectOption("triangle");
    await controls.getByLabel("Amplitude pico a pico (V)", { exact: true }).fill("4");
    await controls.getByLabel("Offset (V)", { exact: true }).fill("1");
    await controls.getByLabel("Duty cycle / subida (%)", { exact: true }).fill("25");
    const triangle = await circuit();
    assert.equal(triangle.components.find((c) => c.ref === "V1").kind, "vpulse");
    const netlist = await api("/schematic/netlist", { schematic: triangle });
    assert.match(netlist.netlist, /PULSE\(-1 3 0 0\.00025 0\.00075 0 0\.001\)/i);
    const submitted = page.waitForResponse(
      (r) => r.url().endsWith("/schematic/simulate") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Simular", exact: true }).click();
    const simulation = await (await submitted).json();
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll(".simulation-output b")].some(
          (el) => el.textContent === "Concluída",
        ),
      undefined,
      { timeout: 120000 },
    );
    const job = await (
      await page.request.get(BASE + "/api/v1/simulations/" + simulation.job_id)
    ).json();
    const tran = job.plots.find((p) => p.kind === "tran");
    const trace = await (
      await page.request.get(
        BASE +
          "/api/v1/simulations/" +
          job.id +
          "/plots/" +
          tran.name +
          "?vectors=v(in)&form=real&max_points=10000",
      )
    ).json();
    const xs = trace.x.values,
      ys = trace.traces["v(in)"].values;
    const nearest = xs.reduce(
      (best, value, i) => (Math.abs(value - 0.00025) < Math.abs(xs[best] - 0.00025) ? i : best),
      0,
    );
    assert.ok(
      Math.abs(ys[nearest] - 3) < 0.05,
      "triangular source reaches its peak at the configured duty fraction",
    );
    await page.getByRole("tab", { name: "Osciloscópio de bancada", exact: true }).click();
    await page.waitForSelector(".instrument-screen polyline", { state: "attached" });
    await page
      .getByRole("combobox", { name: "Canais do osciloscópio", exact: true })
      .selectOption("4");
    assert.equal(await page.locator(".scope-channel-grid fieldset").count(), 4);
    await page.locator(".scope-channel-grid fieldset").nth(2).getByRole("checkbox").check();
    await page.locator(".scope-channel-grid fieldset").nth(3).getByRole("checkbox").check();
    await page.getByRole("combobox", { name: "Sinal CH4", exact: true }).selectOption("v(in)");
    await page.waitForSelector('polyline[data-channel="4"]');
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    assert.equal(await page.getByRole("button", { name: "Run", exact: true }).count(), 1);
    await shot("bench-03-oscilloscope.png");
    await page
      .getByRole("navigation", { name: "Etapas do simulador" })
      .getByRole("button", { name: /^Circuito/ })
      .click();
    await page.getByRole("button", { name: "Protoboard", exact: true }).click();
    await page.waitForFunction(() =>
      [...document.querySelectorAll(".instrument-display output")].some(
        (el) =>
          el.getAttribute("aria-label")?.startsWith("Corrente drenada") &&
          !el.textContent.includes("—"),
      ),
    );
    await page
      .getByRole("combobox", { name: "Adicionar instrumento", exact: true })
      .selectOption("scope2");
    assert.equal(await page.locator(".scope-miniature").count(), 1);
    await page.getByRole("button", { name: "Remover osciloscópio", exact: true }).click();
    assert.equal(await page.locator(".bench-scope").count(), 0);
    await shot("bench-04-readings.png");

    await navigation.getByRole("button", { name: "Análise de Projetos", exact: true }).click();
    await page.waitForFunction(
      () => !document.querySelector(".project-circuit-actions button")?.disabled,
    );
    const names = ["Original da bancada", "Cópia editada da bancada"];
    page.on("dialog", (d) => d.accept(d.type() === "prompt" ? (names.shift() ?? "") : undefined));
    await page.getByRole("button", { name: "Salvar como…", exact: true }).click();
    await page.waitForSelector("text=Original da bancada");
    await page.getByRole("button", { name: "Editar circuito do projeto", exact: true }).click();
    await page.waitForSelector(".schematic-page");
    const projectPicker = page.getByRole("combobox", {
      name: "Selecionar componente",
      exact: true,
    });
    const options = await projectPicker.locator("option").allTextContents();
    const resistorLabel = options.find((t) => / · Resistor/.test(t));
    assert.ok(resistorLabel, "converted project has an editable resistor");
    await projectPicker.selectOption({ label: resistorLabel });
    const beforeCount = await projectPicker.locator("option").count();
    await page.locator(".properties").getByRole("button", { name: "Apagar", exact: true }).click();
    assert.equal(await projectPicker.locator("option").count(), beforeCount - 1);
    await page.getByRole("button", { name: "Salvar como…", exact: true }).click();
    await page.waitForSelector("text=Cópia editada da bancada");
    const list = await (await page.request.get(BASE + "/api/v1/projects")).json();
    const original = list.find((p) => p.name === "Original da bancada");
    const copy = list.find((p) => p.name === "Cópia editada da bancada");
    assert.notEqual(original.id, copy.id);
    const originalDoc = await (
      await page.request.get(BASE + "/api/v1/projects/" + original.id)
    ).json();
    const copyDoc = await (await page.request.get(BASE + "/api/v1/projects/" + copy.id)).json();
    assert.equal(originalDoc.current.schematic, null);
    assert.equal(copyDoc.current.schematic.components.length, beforeCount - 2);
    await page.getByRole("button", { name: "Abrir…", exact: true }).click();
    await page
      .getByRole("dialog", { name: "Abrir projeto" })
      .getByRole("cell", { name: "Original da bancada", exact: true })
      .click();
    await page.getByRole("button", { name: "Abrir…", exact: true }).click();
    await page
      .getByRole("dialog", { name: "Abrir projeto" })
      .getByRole("cell", { name: "Cópia editada da bancada", exact: true })
      .click();
    await page.waitForSelector(".schematic-page");
    assert.equal(
      await page
        .getByRole("combobox", { name: "Selecionar componente", exact: true })
        .locator("option")
        .count(),
      beforeCount - 1,
    );
    await shot("bench-05-edit-project.png");
    await page.getByRole("button", { name: "Enviar à protoboard", exact: true }).click();
    await page.waitForSelector(".bb-board-panel");
    assert.equal((await circuit()).components.length, copyDoc.current.schematic.components.length);
    assert.equal(await page.locator(".bb-board-panel").count(), 2);
    assert.deepEqual(errors, []);
    console.log("Virtual bench E2E: ok");
  } catch (e) {
    if (OUT)
      await page.screenshot({ path: OUT + "bench-99-failure.png", fullPage: true }).catch(() => {});
    throw e;
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
