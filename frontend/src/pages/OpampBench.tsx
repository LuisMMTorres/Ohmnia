import { type ReactNode, useEffect, useRef, useState } from "react";
import { bench, OpampBenchIn, OpampBenchOut } from "../api";
import { CalcSteps } from "../components/CalcSteps";
import { SignalPlot } from "../components/SignalPlot";
import { formatEng, formatRaw } from "../format";
import { num } from "./BenchPage";
import { useComponents } from "./TransistorBench";

/** BD-AMPOP and BV-AMPOP: the op-amp macromodel and the virtual laboratory tests. */
export function OpampBench({ selector }: { selector: ReactNode }) {
  const [a0, setA0] = useState("200000");
  const [gbw, setGbw] = useState("1");
  const [sr, setSr] = useState("0,5");
  const [vos, setVos] = useState("1");
  const [ib, setIb] = useState("80");
  const [ios, setIos] = useState("20");
  const [rin, setRin] = useState("2");
  const [cmrr, setCmrr] = useState("90");
  const [psrr, setPsrr] = useState("96");
  const [drop, setDrop] = useState("2");
  const [vs, setVs] = useState("15");
  const [componentId, setComponentId] = useState("");
  const [result, setResult] = useState<OpampBenchOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const components = useComponents("opamp");
  const latest = useRef(0);

  const body = (): OpampBenchIn => ({
    model: {
      A0: num(a0),
      GBW: { value: num(gbw), unit: "MHz" },
      SR: { value: num(sr), unit: "V/us" },
      Vos: { value: num(vos), unit: "mV" },
      Ib: { value: num(ib), unit: "nA" },
      Ios: { value: num(ios), unit: "nA" },
      Rin: { value: num(rin), unit: "Mohm" },
      CMRR_db: num(cmrr),
      PSRR_db: num(psrr),
      drop: { value: num(drop), unit: "V" },
    },
    VS: { value: num(vs), unit: "V" },
    component_id: componentId || null,
  });

  useEffect(() => {
    const b = body();
    const handle = window.setTimeout(() => {
      const ticket = ++latest.current;
      setBusy(true);
      bench
        .opamp(b)
        .then((res) => {
          if (ticket !== latest.current) return;
          setResult(res);
          setError(null);
        })
        .catch((e: Error) => {
          if (ticket === latest.current) setError(e.message);
        })
        .finally(() => {
          if (ticket === latest.current) setBusy(false);
        });
    }, 400);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a0, gbw, sr, vos, ib, ios, rin, cmrr, psrr, drop, vs, componentId]);

  const fields: [string, string, (v: string) => void][] = [
    ["Ganho em malha aberta A0 (V/V)", a0, setA0],
    ["Produto ganho-banda GBW (MHz)", gbw, setGbw],
    ["Taxa de inclinação SR (V/µs)", sr, setSr],
    ["Tensão de offset VOS (mV)", vos, setVos],
    ["Corrente de polarização IB (nA)", ib, setIb],
    ["Corrente de offset IOS (nA)", ios, setIos],
    ["Resistência de entrada Rin (MΩ)", rin, setRin],
    ["CMRR (dB)", cmrr, setCmrr],
    ["PSRR (dB)", psrr, setPsrr],
    ["Excursão: queda até cada trilho (V)", drop, setDrop],
  ];

  return (
    <main className="two-col">
      <section className="panel editor">
        {selector}
        <h2>Bancada: amplificador operacional</h2>
        <p className="small muted">
          Modelo de polo único (A0, GBW), com R<sub>in</sub>, V<sub>OS</sub>, correntes de
          polarização, CMRR e PSRR referidos à entrada, slew rate e excursão. Os ensaios de
          laboratório rodam no ngspice e cada um deve recuperar o parâmetro do modelo.
        </p>
        <label>
          Usar o datasheet de
          <select value={componentId} onChange={(e) => setComponentId(e.target.value)}>
            <option value="">nenhum (valores abaixo)</option>
            {components.map((d) => (
              <option key={d.id} value={d.id}>
                {d.part_number} ({d.manufacturer})
              </option>
            ))}
          </select>
        </label>
        <label>
          Alimentação ± (V)
          <input value={vs} onChange={(e) => setVs(e.target.value)} />
        </label>
        <h3>Modelo</h3>
        {fields.map(([label, value, set]) => (
          <label key={label}>
            {label}
            <input value={value} disabled={!!componentId} onChange={(e) => set(e.target.value)} />
          </label>
        ))}
        {result && (
          <details>
            <summary>Netlists dos ensaios</summary>
            {Object.entries(result.netlists).map(([k, n]) => (
              <pre key={k} className="small">
                {n}
              </pre>
            ))}
          </details>
        )}
      </section>
      <section className="panel">
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {busy && <p className="small muted">Rodando os ensaios no simulador…</p>}
        {result && (
          <>
            <h3>Ganho em malha aberta A(f)</h3>
            <SignalPlot
              x={result.bode_f.values}
              xUnit="Hz"
              xLabel="Frequência"
              xLog
              traces={[{ name: "|A|", unit: "dB", values: result.bode_mag_db.values }]}
              height={220}
            />
            <SignalPlot
              x={result.bode_f.values}
              xUnit="Hz"
              xLabel="Frequência"
              xLog
              traces={[{ name: "Fase", unit: "°", values: result.bode_phase.values }]}
              height={160}
            />
            <h3>Resposta ao degrau (seguidor)</h3>
            <SignalPlot
              x={result.step_t.values}
              xUnit="µs"
              xLabel="Tempo"
              traces={[
                { name: "Entrada", unit: "V", values: result.step_in.values },
                { name: "Saída", unit: "V", values: result.step_out.values },
              ]}
              height={240}
            />
            <h3>Ensaios (BV-AMPOP)</h3>
            <table className="params">
              <thead>
                <tr>
                  <th>Ensaio</th>
                  <th>Medido</th>
                  <th>Modelo</th>
                  <th>Erro</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {result.tests.map((t) => (
                  <tr key={t.id} title={t.method}>
                    <td>{t.name}</td>
                    <td>{formatEng(t.measured.value, t.measured.unit, 5)}</td>
                    <td>{formatEng(t.expected.value, t.expected.unit, 5)}</td>
                    <td>{formatRaw(Number(t.error_pct.toFixed(3)), "%")}</td>
                    <td>{t.ok ? "ok" : `fora (${formatRaw(t.tolerance_pct, "%")})`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {result.warnings
              .filter((w, i, all) => all.indexOf(w) === i)
              .map((w) => (
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
