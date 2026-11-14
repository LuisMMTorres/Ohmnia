import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { bench, PnBenchIn, PnOut } from "../api";
import { CalcSteps } from "../components/CalcSteps";
import { SignalPlot, Trace } from "../components/SignalPlot";
import { num } from "./BenchPage";

type View = "depletion" | "field" | "capacitance" | "ni" | "iv";

const VIEWS: [View, string][] = [
  ["depletion", "Largura da depleção × VR"],
  ["field", "Campo elétrico máximo × VR"],
  ["capacitance", "Capacitância de depleção × VR"],
  ["ni", "Concentração intrínseca ni × T"],
  ["iv", "Corrente direta (Shockley)"],
];

/** BD-PN: abrupt junction physics (depletion, field, capacitance, ni(T), Shockley). */
export function PnBench({ selector }: { selector: ReactNode }) {
  const [na, setNa] = useState("1e17");
  const [nd, setNd] = useState("1e16");
  const [area, setArea] = useState("1e-4");
  const [dn, setDn] = useState("30");
  const [dp, setDp] = useState("10");
  const [ln, setLn] = useState("10");
  const [lp, setLp] = useState("20");
  const [temp, setTemp] = useState("300");
  const [vr, setVr] = useState("5");
  const [vrMax, setVrMax] = useState("20");
  const [b, setB] = useState("7,3e15");
  const [eg, setEg] = useState("1,12");
  const [eps, setEps] = useState("11,7");
  const [view, setView] = useState<View>("depletion");
  const [result, setResult] = useState<PnOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  useEffect(() => {
    const body: PnBenchIn = {
      NA: { value: num(na), unit: "1/cm**3" },
      ND: { value: num(nd), unit: "1/cm**3" },
      area: { value: num(area), unit: "cm**2" },
      Dn: { value: num(dn), unit: "cm**2/s" },
      Dp: { value: num(dp), unit: "cm**2/s" },
      Ln: { value: num(ln), unit: "um" },
      Lp: { value: num(lp), unit: "um" },
      B: { value: num(b), unit: "1/cm**3/K**1.5" },
      Eg: { value: num(eg), unit: "eV" },
      eps_r: num(eps),
      T: { value: num(temp), unit: "K" },
      vr: { value: num(vr), unit: "V" },
      vr_max: { value: num(vrMax), unit: "V" },
    };
    const handle = window.setTimeout(() => {
      const ticket = ++latest.current;
      bench
        .pn(body)
        .then((r) => {
          if (ticket !== latest.current) return;
          setResult(r);
          setError(null);
        })
        .catch((e: Error) => {
          if (ticket === latest.current) setError(e.message);
        });
    }, 200);
    return () => window.clearTimeout(handle);
  }, [na, nd, area, dn, dp, ln, lp, temp, vr, vrMax, b, eg, eps]);

  const plot = useMemo(() => {
    if (!result) return null;
    const vrAxis = { x: result.vr.values, xUnit: "V", xLabel: "Tensão reversa" };
    const one = (name: string, v: { values: number[]; unit: string }): Trace[] => [
      { name, unit: v.unit, values: v.values },
    ];
    switch (view) {
      case "depletion":
        return {
          ...vrAxis,
          yLog: false,
          traces: Object.entries(result.depletion).map(([n, v]) => ({
            name: n,
            unit: "um",
            values: v.values,
          })),
        };
      case "field":
        return { ...vrAxis, yLog: false, traces: one("Campo máximo", result.field) };
      case "capacitance":
        return { ...vrAxis, yLog: false, traces: one("Cj", result.capacitance) };
      case "ni":
        return {
          x: result.temperature.values,
          xUnit: "K",
          xLabel: "Temperatura",
          yLog: true,
          traces: one("ni", result.ni),
        };
      case "iv":
        return {
          x: result.v.values,
          xUnit: "V",
          xLabel: "Tensão direta",
          yLog: true,
          traces: one("I", {
            values: result.current.values.map((v) => (v > 0 ? v : NaN)),
            unit: "A",
          }),
        };
    }
  }, [result, view]);

  const fields: [string, string, (v: string) => void][] = [
    ["Dopagem do lado p, NA (cm⁻³)", na, setNa],
    ["Dopagem do lado n, ND (cm⁻³)", nd, setNd],
    ["Área da junção (cm²)", area, setArea],
    ["Temperatura (K)", temp, setTemp],
    ["Tensão reversa no ponto de cálculo VR (V)", vr, setVr],
    ["VR máxima no gráfico (V)", vrMax, setVrMax],
  ];
  const transport: [string, string, (v: string) => void][] = [
    ["Difusividade dos elétrons Dn (cm²/s)", dn, setDn],
    ["Difusividade das lacunas Dp (cm²/s)", dp, setDp],
    ["Comprimento de difusão Ln (µm)", ln, setLn],
    ["Comprimento de difusão Lp (µm)", lp, setLp],
  ];
  const material: [string, string, (v: string) => void][] = [
    ["Constante B (cm⁻³·K⁻³ᐟ²)", b, setB],
    ["Banda proibida Eg (eV)", eg, setEg],
    ["Permissividade relativa εr", eps, setEps],
  ];
  const inputs = (list: [string, string, (v: string) => void][]) =>
    list.map(([label, value, set]) => (
      <label key={label}>
        {label}
        <input value={value} onChange={(e) => set(e.target.value)} />
      </label>
    ));

  return (
    <main className="two-col">
      <section className="panel editor">
        {selector}
        <h2>Bancada: junção PN</h2>
        <p className="small muted">
          Junção abrupta de silício: concentração intrínseca, tensão de barreira, largura da
          depleção, campo elétrico, capacitância e corrente de saturação a partir da dopagem e da
          temperatura. A capacitância é conferida com o diodo equivalente no ngspice.
        </p>
        {inputs(fields)}
        <details>
          <summary>Transporte (corrente de saturação)</summary>
          <p className="small muted">Valores de exemplo, ajustáveis.</p>
          {inputs(transport)}
        </details>
        <details>
          <summary>Material</summary>
          <p className="small muted">
            Padrão: silício, com os valores de Sedra &amp; Smith (capítulo de semicondutores).
          </p>
          {inputs(material)}
        </details>
        <label>
          Gráfico
          <select value={view} onChange={(e) => setView(e.target.value as View)}>
            {VIEWS.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {result && (
          <details>
            <summary>Diodo SPICE equivalente</summary>
            <pre className="small">{result.spice_model}</pre>
          </details>
        )}
      </section>
      <section className="panel">
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {result && plot && (
          <>
            <SignalPlot
              x={plot.x}
              xUnit={plot.xUnit}
              xLabel={plot.xLabel}
              yLog={plot.yLog}
              traces={plot.traces}
              height={400}
            />
            {result.warnings.map((w) => (
              <p key={w} className="small note">
                {w}
              </p>
            ))}
            <h3>Memória de cálculo</h3>
            <CalcSteps steps={result.steps} />
          </>
        )}
      </section>
    </main>
  );
}
