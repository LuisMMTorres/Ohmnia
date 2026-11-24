import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { bench, Quantity, ThyristorBenchIn, WaveOut } from "../api";
import { CalcSteps } from "../components/CalcSteps";
import { SignalPlot, Trace } from "../components/SignalPlot";
import { formatEng, formatRaw } from "../format";
import { num } from "./BenchPage";
import { useComponents } from "./TransistorBench";

type Kind = "scr" | "triac";
type GateMode = "positivo" | "negativo" | "acompanha";

const GATE_MODES: [GateMode, string][] = [
  ["positivo", "Pulsos positivos (Q1 e Q4)"],
  ["negativo", "Pulsos negativos (Q2 e Q3)"],
  ["acompanha", "Acompanham MT2 (Q1 e Q3)"],
];

function text(q: Quantity | string | undefined, digits = 4): string {
  if (q === undefined || typeof q === "string") return "";
  return formatRaw(Number(q.value.toPrecision(digits)), "");
}

/** BD-TIR: SCR and TRIAC with a resistive load and gate pulses at the firing angle α. */
export function ThyristorBench({ selector }: { selector: ReactNode }) {
  const [kind, setKind] = useState<Kind>("scr");
  const [vt0, setVt0] = useState("1");
  const [rt, setRt] = useState("50");
  const [igt, setIgt] = useState("5");
  const [ih, setIh] = useState("5");
  const [il, setIl] = useState("10");
  const [vrms, setVrms] = useState("127");
  const [freq, setFreq] = useState("60");
  const [r, setR] = useState("100");
  const [alpha, setAlpha] = useState("60");
  const [ig, setIg] = useState("20");
  const [tw, setTw] = useState("100");
  const [mode, setMode] = useState<GateMode>("positivo");
  const [componentId, setComponentId] = useState("");
  const [result, setResult] = useState<WaveOut | null>(null);
  const [fitResult, setFitResult] = useState<WaveOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const components = useComponents(kind === "scr" ? "thyristor.scr" : "thyristor.triac");
  // Responses can arrive out of order: only the latest request may update the page.
  const latest = useRef(0);

  const body = (fit: boolean): ThyristorBenchIn | null => {
    const igts = igt
      .split(/[;\s]+/)
      .filter(Boolean)
      .map((t) => ({ value: num(t), unit: "mA" }));
    const first = igts[0];
    // one value: the same IGT in every quadrant (an SCR only uses Q1)
    while (igts.length === 1 && first) igts.push(first, first, first);
    if (igts.length !== 4 || igts.some((g) => Number.isNaN(g.value))) {
      setError("Informe IGT em mA: um valor, ou um por quadrante (Q1; Q2; Q3; Q4)");
      return null;
    }
    return {
      model: {
        kind,
        VT0: { value: num(vt0), unit: "V" },
        rT: { value: num(rt), unit: "mohm" },
        IGT: igts,
        IH: { value: num(ih), unit: "mA" },
        IL: { value: num(il), unit: "mA" },
      },
      drive: {
        Vm: { value: num(vrms) * Math.SQRT2, unit: "V" },
        f: { value: num(freq), unit: "Hz" },
        R: { value: num(r), unit: "ohm" },
        alpha: { value: num(alpha), unit: "deg" },
        IG: { value: num(ig), unit: "mA" },
        tw: { value: num(tw), unit: "us" },
        gate_mode: mode,
      },
      component_id: componentId || null,
      fit,
    };
  };

  useEffect(() => {
    const b = body(false);
    if (!b) return;
    const handle = window.setTimeout(() => {
      const ticket = ++latest.current;
      bench
        .thyristor(b)
        .then((res) => {
          if (ticket !== latest.current) return;
          setResult(res);
          setError(null);
        })
        .catch((e: Error) => {
          if (ticket === latest.current) setError(e.message);
        });
    }, 200);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, vt0, rt, igt, ih, il, vrms, freq, r, alpha, ig, tw, mode, componentId]);

  const fit = () => {
    const b = body(true);
    if (!b) return;
    bench
      .thyristor(b)
      .then((res) => {
        setFitResult(res);
        const m = res.model;
        setRt(text(m.rT));
        setIh(text(m.IH));
        setIl(text(m.IL));
        const q = ["IGT_Q1", "IGT_Q2", "IGT_Q3", "IGT_Q4"].filter((k) => m[k] !== undefined);
        setIgt(q.map((k) => text(m[k])).join("; "));
      })
      .catch((e: Error) => setError(e.message));
  };
  const edit = (setter: (v: string) => void) => (v: string) => {
    setFitResult(null);
    setter(v);
  };

  const plots = useMemo(() => {
    if (!result) return null;
    const pick = (names: string[]): Trace[] =>
      names.flatMap((n) => {
        const v = result.traces[n];
        return v ? [{ name: n, unit: v.unit, values: v.values }] : [];
      });
    return {
      voltages: pick(["Tensão da fonte", "Tensão na carga", "Tensão no tiristor"]),
      current: pick(["Corrente"]),
      gate: pick(["Corrente de gate"]),
    };
  }, [result]);

  const shown =
    result && fitResult
      ? [
          ...fitResult.steps.filter((s) => /^(IGT|IH|rT_fit)/.test(s.id)),
          ...result.steps.filter((s) => !/^(IGT|IH|rT_fit)/.test(s.id)),
        ]
      : (result?.steps ?? []);
  const isFit = (id: string) => /^(IGT|IH|rT_fit)/.test(id);
  const fields: [string, string, (v: string) => void][] = [
    ["Tensão de limiar VT0 (V)", vt0, edit(setVt0)],
    ["Resistência de condução rT (mΩ)", rt, edit(setRt)],
    [
      kind === "scr" ? "Corrente de disparo IGT (mA)" : "IGT por quadrante Q1; Q2; Q3; Q4 (mA)",
      igt,
      edit(setIgt),
    ],
    ["Corrente de manutenção IH (mA)", ih, edit(setIh)],
    ["Corrente de travamento IL (mA)", il, edit(setIl)],
  ];
  const circuit: [string, string, (v: string) => void][] = [
    ["Tensão eficaz da fonte (V)", vrms, setVrms],
    ["Frequência (Hz)", freq, setFreq],
    ["Resistência de carga R (Ω)", r, setR],
    ["Ângulo de disparo α (°)", alpha, setAlpha],
    ["Corrente do pulso de gate IG (mA)", ig, setIg],
    ["Largura do pulso tw (µs)", tw, setTw],
  ];

  return (
    <main className="two-col">
      <section className="panel editor">
        {selector}
        <h2>Bancada: tiristores</h2>
        <p className="small muted">
          SCR ou TRIAC com carga resistiva e pulso de gate no ângulo α. O modelo dispara quando a
          corrente de gate atinge I<sub>GT</sub> do quadrante, trava se a corrente na carga chegar a
          I<sub>L</sub> durante o pulso e bloqueia quando ela cai abaixo de I<sub>H</sub>; em
          condução, v<sub>T</sub> = V<sub>T0</sub> + r<sub>T</sub>·i. O mesmo modelo é conferido no
          ngspice.
        </p>
        <label>
          Dispositivo
          <select
            value={kind}
            onChange={(e) => {
              setFitResult(null);
              setComponentId("");
              setKind(e.target.value as Kind);
              setIgt(e.target.value === "scr" ? "5" : "5; 5; 5; 7");
            }}
          >
            <option value="scr">SCR (meia onda)</option>
            <option value="triac">TRIAC (controlador CA)</option>
          </select>
        </label>
        <h3>Modelo</h3>
        {fields.map(([label, value, set]) => (
          <label key={label}>
            {label}
            <input value={value} onChange={(e) => set(e.target.value)} />
          </label>
        ))}
        <h3>Circuito e disparo</h3>
        {circuit.map(([label, value, set]) => (
          <label key={label}>
            {label}
            <input value={value} onChange={(e) => set(e.target.value)} />
          </label>
        ))}
        {kind === "triac" && (
          <label>
            Polaridade dos pulsos de gate
            <select value={mode} onChange={(e) => setMode(e.target.value as GateMode)}>
              {GATE_MODES.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Comparar com o datasheet de
          <select
            value={componentId}
            onChange={(e) => {
              setFitResult(null);
              setComponentId(e.target.value);
            }}
          >
            <option value="">nenhum</option>
            {components.map((d) => (
              <option key={d.id} value={d.id}>
                {d.part_number} ({d.manufacturer})
              </option>
            ))}
          </select>
        </label>
        <button disabled={!componentId} onClick={fit}>
          Ajustar ao datasheet
        </button>
        {result && (
          <details>
            <summary>Subcircuito SPICE equivalente</summary>
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
        {result && plots && (
          <>
            <SignalPlot
              x={result.t.values}
              xUnit="ms"
              xLabel="Tempo"
              traces={plots.voltages}
              height={300}
            />
            <SignalPlot
              x={result.t.values}
              xUnit="ms"
              xLabel="Tempo"
              traces={plots.current}
              height={200}
            />
            <SignalPlot
              x={result.t.values}
              xUnit="ms"
              xLabel="Tempo"
              traces={plots.gate}
              height={160}
            />
            <table className="params">
              <tbody>
                <tr>
                  <th>Tensão média na carga</th>
                  <td>
                    {formatEng(
                      // below the integration noise: show a clean zero (TRIAC, symmetric wave)
                      Math.abs(result.summary.Vavg.value) < 1e-6 * result.summary.Vrms.value
                        ? 0
                        : result.summary.Vavg.value,
                      "V",
                      4,
                    )}
                  </td>
                </tr>
                <tr>
                  <th>Tensão eficaz na carga</th>
                  <td>{formatEng(result.summary.Vrms.value, "V", 4)}</td>
                </tr>
                <tr>
                  <th>Condução por período</th>
                  <td>{formatRaw(Number(result.summary.conduction.value.toFixed(1)), "°")}</td>
                </tr>
              </tbody>
            </table>
            <p className="small muted">
              Valores do último período simulado, com o modelo da bancada. A memória de cálculo traz
              as expressões do tiristor ideal para comparação.
            </p>
            {[...(fitResult?.warnings ?? []), ...result.warnings]
              .filter((w, i, all) => all.indexOf(w) === i)
              .map((w) => (
                <p key={w} className="small note">
                  {w}
                </p>
              ))}
            {shown.some((s) => isFit(s.id)) && (
              <>
                <h3>Ajuste ao datasheet</h3>
                <CalcSteps steps={shown.filter((s) => isFit(s.id))} />
              </>
            )}
            <h3>Memória de cálculo</h3>
            <CalcSteps steps={shown.filter((s) => !isFit(s.id))} />
          </>
        )}
      </section>
    </main>
  );
}
