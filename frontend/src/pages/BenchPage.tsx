import { type ReactNode, useEffect, useMemo, useState } from "react";
import { bench, catalog, ComponentSummary, DiodeBenchOut } from "../api";
import { CalcSteps } from "../components/CalcSteps";
import { SignalPlot, Trace } from "../components/SignalPlot";
import { BjtBench, MosfetBench } from "./TransistorBench";
import { ZenerBench } from "./ZenerBench";

export function num(text: string): number {
  return Number(text.replace(",", "."));
}

type Device = "diodo" | "zener" | "tbj" | "mosfet";

export function BenchPage() {
  const [device, setDevice] = useState<Device>("diodo");
  const selector = (
    <div className="tabs">
      {(
        [
          ["diodo", "Diodo de junção"],
          ["zener", "Diodo Zener"],
          ["tbj", "TBJ"],
          ["mosfet", "MOSFET"],
        ] as const
      ).map(([id, label]) => (
        <button
          key={id}
          className={`tab ${device === id ? "active" : ""}`}
          onClick={() => setDevice(id)}
        >
          {label}
        </button>
      ))}
    </div>
  );
  if (device === "zener") return <ZenerBench selector={selector} />;
  if (device === "tbj") return <BjtBench selector={selector} />;
  if (device === "mosfet") return <MosfetBench selector={selector} />;
  return <DiodeBench selector={selector} />;
}

function DiodeBench({ selector }: { selector: ReactNode }) {
  const [isValue, setIsValue] = useState("10");
  const [isUnit, setIsUnit] = useState("nA");
  const [n, setN] = useState("1,8");
  const [rs, setRs] = useState("0,05");
  const [temps, setTemps] = useState("25; 100");
  const [vMax, setVMax] = useState("1,4");
  const [logScale, setLogScale] = useState(true);
  const [componentId, setComponentId] = useState("");
  const [diodes, setDiodes] = useState<ComponentSummary[]>([]);
  const [result, setResult] = useState<DiodeBenchOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    catalog
      .list({ category: "diode" })
      .then((list) => setDiodes(list.filter((d) => d.category !== "diode.zener")))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const temperatures = temps
      .split(/[;\s]+/)
      .filter(Boolean)
      .map((t) => ({ value: num(t), unit: "degC" }));
    if (temperatures.some((t) => Number.isNaN(t.value)) || temperatures.length === 0) {
      setError("Temperaturas inválidas");
      return;
    }
    const handle = window.setTimeout(() => {
      bench
        .diode({
          model: {
            Is: { value: num(isValue), unit: isUnit },
            n: num(n),
            Rs: { value: num(rs), unit: "ohm" },
          },
          temperatures,
          v_min: { value: 0, unit: "V" },
          v_max: { value: num(vMax), unit: "V" },
          points: 500,
          component_id: componentId || null,
        })
        .then((r) => {
          setResult(r);
          setError(null);
        })
        .catch((e: Error) => setError(e.message));
    }, 200);
    return () => window.clearTimeout(handle);
  }, [isValue, isUnit, n, rs, temps, vMax, componentId]);

  const traces: Trace[] = useMemo(() => {
    if (!result) return [];
    const clean = (values: number[]) => values.map((v) => (logScale && !(v > 0) ? null : v));
    const curves = Object.entries(result.curves).map(([label, vec]) => ({
      name: `Modelo, ${label}`,
      unit: "A",
      values: clean(vec.values),
    }));
    const markers = result.markers.map((m) => ({
      name: m.label,
      unit: "A",
      points: true,
      values: result.v.values.map((v) => (Math.abs(v - m.v.value) < 1e-12 ? m.i.value : null)),
    }));
    return [...curves, ...markers];
  }, [result, logScale]);

  return (
    <main className="two-col">
      <section className="panel editor">
        {selector}
        <h2>Bancada: diodo de junção</h2>
        <p className="small muted">
          Equação de Shockley com resistência série e dependência térmica do modelo SPICE. Os
          parâmetros do modelo são ajustáveis e didáticos; não vêm do datasheet.
        </p>
        <label>
          Corrente de saturação Is (a 27 °C)
          <span className="row">
            <input value={isValue} onChange={(e) => setIsValue(e.target.value)} />
            <select value={isUnit} onChange={(e) => setIsUnit(e.target.value)}>
              <option value="fA">fA</option>
              <option value="pA">pA</option>
              <option value="nA">nA</option>
              <option value="uA">µA</option>
            </select>
          </span>
        </label>
        <label>
          Coeficiente de emissão n
          <input value={n} onChange={(e) => setN(e.target.value)} />
        </label>
        <label>
          Resistência série Rs (Ω)
          <input value={rs} onChange={(e) => setRs(e.target.value)} />
        </label>
        <label>
          Temperaturas de junção (°C, separadas por ;)
          <input value={temps} onChange={(e) => setTemps(e.target.value)} />
        </label>
        <label>
          Tensão máxima no gráfico (V)
          <input value={vMax} onChange={(e) => setVMax(e.target.value)} />
        </label>
        <label>
          Comparar com o datasheet de
          <select value={componentId} onChange={(e) => setComponentId(e.target.value)}>
            <option value="">nenhum</option>
            {diodes.map((d) => (
              <option key={d.id} value={d.id}>
                {d.part_number} ({d.manufacturer})
              </option>
            ))}
          </select>
        </label>
        <label className="inline">
          <input
            type="checkbox"
            checked={logScale}
            onChange={(e) => setLogScale(e.target.checked)}
          />
          Corrente em escala logarítmica
        </label>
        {result && (
          <details>
            <summary>Modelo SPICE equivalente</summary>
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
        {result && (
          <>
            <SignalPlot
              x={result.v.values}
              xUnit="V"
              xLabel="Tensão direta"
              yLog={logScale}
              traces={traces}
              height={420}
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
