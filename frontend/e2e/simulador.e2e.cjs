const { chromium } = require("playwright");
/**
 * E2E of the free simulator (phase 7): every example simulates, Bode/FFT/Monte Carlo/worst
 * case/STEP views render, a SPICE netlist imports, and a circuit drawn from scratch gives the
 * expected operating point. Run with scripts/e2e.sh (needs the built front end and ngspice).
 * Set SHOTS=<dir> to also save the screenshots used in the phase report.
 */
const assert = require("node:assert/strict");
const BASE = process.env.BASE || "http://127.0.0.1:8766";
const OUT = process.env.SHOTS || "";
(async () => {
  let b, p;
  try {
    b = await chromium.launch({
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
    });
    p = await b.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    const errs = [];
    p.on("pageerror", (e) => errs.push(String(e)));
    p.on("response", (r) => {
      if (r.status() >= 400) errs.push(`HTTP ${r.status()} ${r.url()}`);
    });
    p.on("console", (m) => {
      if (m.type() === "error") errs.push(m.text());
    });
    await p.goto(BASE + "/#simulator");
    await p.evaluate(() => localStorage.clear());
    await p.reload();
    await p.waitForSelector(".schematic-canvas", { timeout: 20000 });
    const nodeToggle = p.getByRole("checkbox", { name: "Exibir nomes dos nós" });
    assert.equal(await p.locator(".node-annotations text").count(), 0);
    await nodeToggle.check();
    await p.waitForSelector(".node-annotations text");
    assert.ok((await p.locator(".node-annotations text").allTextContents()).includes("0"));
    await nodeToggle.uncheck();
    await p.waitForFunction(() => document.querySelectorAll(".node-annotations text").length === 0);
    const steps = p.getByRole("navigation", { name: "Etapas do simulador" });
    assert.equal(await steps.getByRole("button").count(), 3);
    assert.equal(await steps.getByRole("button", { name: /Resultados/ }).isDisabled(), true);
    await steps.getByRole("button", { name: /Configurar análise/ }).click();
    assert.equal(
      await p.locator(".analysis-panel").evaluate((el) => el === document.activeElement),
      true,
    );
    assert.equal(await p.locator(".simulation-output").isVisible(), false);
    const circuitBounds = await p.locator(".circuit-workspace").boundingBox();
    const analysisBounds = await p.locator(".analysis-panel").boundingBox();
    assert.ok(
      analysisBounds.x >= circuitBounds.x + circuitBounds.width,
      "analysis opens beside circuit",
    );
    assert.ok(Math.abs(analysisBounds.y - circuitBounds.y) < 2, "analysis stays at workspace top");
    await steps.getByRole("button", { name: /^Circuito/ }).click();
    const picker = p.getByRole("combobox", { name: "Selecionar componente", exact: true });
    const resistor = await picker
      .locator("option")
      .filter({ hasText: /^R1 ·/ })
      .getAttribute("value");
    await picker.selectOption(resistor);
    assert.equal(await picker.inputValue(), resistor);
    await p.locator(".skip-link").focus();
    await p.keyboard.press("Enter");
    assert.equal(await p.evaluate(() => document.activeElement.id), "workspace-content");
    await p.setViewportSize({ width: 390, height: 844 });
    await p.waitForFunction(() => {
      const canvas = document.querySelector(".schematic-canvas");
      const bounds = canvas.getBoundingClientRect();
      return [...canvas.querySelectorAll(".comp")].every((component) => {
        const rect = component.getBoundingClientRect();
        return rect.left >= bounds.left && rect.right <= bounds.right;
      });
    });
    assert.equal(
      await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      true,
    );
    await p.setViewportSize({ width: 1440, height: 1000 });
    const shot = async (n) => {
      await p.waitForTimeout(700);
      if (OUT) await p.screenshot({ path: OUT + n, fullPage: true });
      console.log("ok", n);
    };
    const example = async (name) => {
      await p.selectOption('select[aria-label="Exemplos"]', name);
      await p.waitForTimeout(400);
    };
    const simulate = async () => {
      await p.click('button:text-is("Simular")');
      await p.waitForFunction(
        () =>
          document.querySelector('.schematic-page > [role="alert"]') ||
          [...document.querySelectorAll(".simulation-output b")].some((el) =>
            /^(Concluída|Falhou)$/.test(el.textContent),
          ),
        undefined,
        { timeout: 300000 },
      );
      if (await p.locator('.schematic-page > [role="alert"]').count())
        throw new Error(await p.locator('.schematic-page > [role="alert"]').innerText());
      if (await p.locator('b:text-is("Falhou")').count())
        throw new Error("simulation failed: " + (await p.locator(".error").first().innerText()));
      await p.waitForTimeout(1200);
    };
    const field = (scope, re) =>
      p
        .locator(scope + " label")
        .filter({ hasText: re })
        .first()
        .locator("select, input")
        .first();
    const mode = async (m) => {
      await p.click(`.results-view button[role=tab]:text-is("${m}")`);
      await p.waitForTimeout(800);
    };
    const analysis = async (re) => {
      const sel = p.locator(".results-view select").first();
      const opts = await sel.locator("option").allTextContents();
      const o = opts.find((t) => re.test(t));
      await sel.selectOption({ label: o });
      await p.waitForTimeout(600);
    };

    await example("Filtro RC passa-baixas");
    await simulate();
    assert.equal(await steps.getByRole("button", { name: /Resultados/ }).isEnabled(), true);
    assert.equal(
      await steps.getByRole("button", { name: /Resultados/ }).getAttribute("aria-current"),
      "step",
    );
    assert.equal(await p.locator(".analysis-panel").isVisible(), false);
    const resultsBounds = await p.locator(".simulation-output").boundingBox();
    const schematicBounds = await p.locator(".circuit-workspace").boundingBox();
    assert.ok(
      resultsBounds.x >= schematicBounds.x + schematicBounds.width,
      "results open beside circuit",
    );
    assert.deepEqual(
      (await p.locator(".vectors label").allTextContents()).map((v) => v.trim()).sort(),
      ["i(c1)", "v(in)", "v(out)"],
    );
    await shot("01-rc-esquematico-osciloscopio.png");
    await analysis(/frequência/i);
    await mode("Bode");
    await shot("02-rc-bode.png");

    await example("Retificador em ponte com filtro");
    await simulate();
    await shot("03-ponte-osciloscopio.png");
    await mode("FFT / THD");
    await field(".results-view", /^Sinal/).selectOption({ label: "i(v1)" });
    await p.click('.results-view button:text-is("Calcular")');
    await p.waitForSelector("text=THD =", { timeout: 30000 });
    assert.match(await p.locator(".results-view").innerText(), /f₀ = 60 Hz/);
    await shot("04-ponte-fft-thd.png");

    await example("Filtro RC: Monte Carlo");
    await simulate();
    await mode("Bode");
    await shot("05-rc-monte-carlo-bode.png");
    await mode("Estatística");
    await field(".results-view", /^Sinal/).selectOption({ label: "v(out)" });
    await field(".results-view", /^Medida/).selectOption("mag_db_at");
    await field(".results-view", /^em/).fill("1k");
    await p.click('.results-view button:text-is("Calcular")');
    await p.waitForTimeout(1500);
    await shot("06-rc-monte-carlo-histograma.png");

    // worst case on the same circuit, configured through the sweep panel
    await steps.getByRole("button", { name: /Configurar análise/ }).click();
    await p.click('button.tab:text-is("Varredura, Monte Carlo e pior caso")');
    await field(".analysis-panel", /^Tipo/).selectOption("worstcase");
    await field(".analysis-panel", /^Análise da medida/).selectOption("ac");
    await field(".analysis-panel", /^Sinal/).fill("v(out)");
    await field(".analysis-panel", /^Medida/).selectOption("mag_db_at");
    await field(".analysis-panel", /^Em x/).fill("1k");
    await simulate();
    await mode("Pior caso");
    {
      // analytic extremes of |H(1 kHz)| with R ±5 % and C ±10 % (see docs/validacao/simulador.md)
      const t = await p.locator(".results-view").innerText();
      assert.match(t, /pior caso mínimo -3,676/);
      assert.match(t, /máximo -2,379/);
    }
    await shot("07-rc-pior-caso.png");

    await example("RLC série: STEP de R");
    await simulate();
    await shot("08-rlc-step.png");

    await example("Ruído térmico com varredura de temperatura");
    await simulate();
    {
      const t = await p.locator(".results-view").innerText();
      assert.match(t, /Ruído/);
      assert.match(t, /onoise_spectrum/);
      assert.ok((await p.locator(".results-view .u-over").count()) > 0, "noise curves plotted");
    }
    await shot("09-ruido-temperatura.png");

    await example("Amplificador emissor comum");
    await simulate();
    await shot("10-emissor-comum-tran.png");
    await analysis(/operação/i);
    await shot("11-emissor-comum-op.png");

    // import a SPICE netlist
    await p.click('button:text-is("Importar netlist")');
    await p.fill(
      ".import-box textarea",
      `Divisor com amp-op ideal (importado)
V1 in 0 SIN(0 1 1k)
R1 in n1 10k
R2 n1 out 47k
E1 out 0 0 n1 1e5
.tran 0 3m 0 5u
.end`,
    );
    await p.click('.import-box button:text-is("Importar")');
    await p.waitForTimeout(800);
    await simulate();
    await shot("12-netlist-importada.png");

    // draw a circuit from scratch: V source, resistor, wires, ground, probe
    await p.click('button:text-is("Novo")');
    await p.getByRole("button", { name: "Adicionar componente", exact: true }).click();
    assert.equal(
      await p
        .getByRole("button", { name: "Recolher biblioteca", exact: true })
        .getAttribute("aria-expanded"),
      "true",
    );
    await p.click('button:text-is("Enquadrar")').catch(() => {});
    const at = async (gx, gy, opts) => {
      await p
        .locator(".schematic-canvas")
        .evaluate((canvas) => canvas.scrollIntoView({ block: "center", behavior: "instant" }));
      // map grid coords through the current view transform
      const pt = await p.evaluate(
        ([gx, gy]) => {
          const s = document.querySelector(".schematic-canvas");
          const g = s.querySelector(":scope > g");
          const m = g.getScreenCTM();
          const P = s.createSVGPoint();
          P.x = gx * 20;
          P.y = gy * 20;
          const r = P.matrixTransform(m);
          return [r.x, r.y];
        },
        [gx, gy],
      );
      assert.ok(
        await p.evaluate(
          ([x, y]) => !!document.elementFromPoint(x, y)?.closest(".schematic-canvas"),
          pt,
        ),
        `drawing point ${gx},${gy} is obscured`,
      );
      await p.mouse.click(pt[0], pt[1], opts);
    };
    await p.click('.palette-item:text-is("Fonte de tensão (CC/CA)")');
    await at(0, 0);
    await p.click('.palette-item:text-is("Resistor")');
    await at(4, -4);
    await p.click('.palette-item:text-is("Resistor")');
    await at(8, 0, {});
    await p.keyboard.press("r");
    await p.click('.palette-item:text-is("Terra")');
    await at(0, 4);
    await p.click('.palette-item:text-is("Terra")');
    await at(8, 4);
    await p.click('.tool:text-is("Fio (W)")');
    await at(0, -2);
    await at(0, -4);
    await at(2, -4);
    await at(6, -4);
    await at(8, -4);
    await at(8, -2);
    await at(0, 2);
    await at(0, 4);
    await at(8, 2);
    await at(8, 4);
    await p.click('.tool:text-is("Ponteira V")');
    await at(8, -4);
    await p.click('.tool:text-is("Selecionar")');
    await steps.getByRole("button", { name: /Configurar análise/ }).click();
    await p.click('button.tab:text-is("Análises")');
    await p.click('button:text-is("+ Ponto de operação (.op)")');
    await simulate();
    await analysis(/operação/i);
    await shot("13-desenho-do-zero-op.png");
    const txt = await p.locator(".results-view").innerText();
    // default source 5 V across two equal default resistors
    assert.match(txt, /v\(n00\d\)\s+2,5 V/);
    assert.deepEqual(errs, [], "console errors or failed requests");
    await example("Filtro RC passa-baixas");
    await steps.getByRole("button", { name: /^Circuito/ }).click();
    await picker.selectOption(
      await picker.locator("option").filter({ hasText: /^R1 ·/ }).getAttribute("value"),
    );
    if (await p.getByRole("button", { name: "Recolher biblioteca", exact: true }).count())
      await p.getByRole("button", { name: "Recolher biblioteca", exact: true }).click();
    await p.evaluate(() => window.scrollTo(0, 0));
    if (OUT) await p.screenshot({ path: OUT + "00-bancada-assistida.png", fullPage: false });
    await p
      .getByRole("navigation", { name: "Seções" })
      .getByRole("button", { name: "Biblioteca", exact: true })
      .click();
    assert.equal(await p.locator(".workspace-intro h2").innerText(), "Biblioteca");
    await p.goBack();
    await p.waitForSelector(".schematic-canvas");
    assert.equal(await p.locator(".workspace-intro h2").innerText(), "Simulador");
    await p.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      true,
    );
    if (OUT) await p.screenshot({ path: OUT + "00-bancada-mobile.png", fullPage: true });
    await p.setViewportSize({ width: 1440, height: 1000 });
    await p.emulateMedia({ colorScheme: "dark" });
    if (OUT) await p.screenshot({ path: OUT + "00-bancada-escura.png", fullPage: false });
    console.log("E2E simulador: ok");
  } catch (error) {
    if (p && OUT) await p.screenshot({ path: OUT + "e2e-failure.png", fullPage: true });
    throw error;
  } finally {
    await b?.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
