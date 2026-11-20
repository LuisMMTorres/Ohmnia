import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  bench,
  PeripheralBenchInfo,
  PeripheralBenchOut,
  PeripheralParam,
  PeripheralPart,
} from "../api";
import { CalcSteps } from "../components/CalcSteps";
import { SignalPlot } from "../components/SignalPlot";
import { formatEng, formatRaw } from "../format";

const GROUPS = ["Sensores", "Atuadores", "Placas e controladores"];

/** BD-PER: sensors, actuators and boards of the simulator library on the device bench. */
export function PeripheralBench({ selector }: { selector: ReactNode }) {
  const [benches, setBenches] = useState<PeripheralBenchInfo[]>([]);
  const [kind, setKind] = useState("lm35");
  const [params, setParams] = useState<Record<string, string>>({});
  const [fixture, setFixture] = useState<Record<string, string>>({});
  const [parts, setParts] = useState<PeripheralPart[]>([]);
  const [partId, setPartId] = useState("");
  const [result, setResult] = useState<PeripheralBenchOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const latest = useRef(0);

  useEffect(() => {
    bench
      .peripherals()
      .then(setBenches)
      .catch((e: Error) => setError(e.message));
  }, []);

  const info = benches.find((b) => b.kind === kind);

  useEffect(() => {
    setParams({});
    setFixture({});
    setPartId("");
    setResult(null);
    setError(null);
    setParts([]);
    if (!info || info.catalogue.length === 0) return;
    bench
      .peripheralParts(kind)
      .then(setParts)
      .catch(() => undefined);
  }, [kind, info]);

  const run = (fresh = false) => {
    const ticket = ++latest.current;
    setBusy(true);
    setError(null);
    const body = fresh
      ? { params: {}, fixture: {}, component_id: null }
      : { params, fixture, component_id: partId || null };
    bench
      .peripheral(kind, body)
      .then((res) => {
        if (ticket !== latest.current) return;
        setResult(res);
      })
      .catch((e: Error) => {
        if (ticket === latest.current) setError(e.message);
      })
      .finally(() => {
        if (ticket === latest.current) setBusy(false);
      });
  };

  // first run of each bench with its defaults
  useEffect(() => {
    if (info) run(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info]);

  const grouped = useMemo(
    () => GROUPS.map((g) => [g, benches.filter((b) => b.group === g)] as const),
    [benches],
  );

  const field = (
    p: PeripheralParam,
    values: Record<string, string>,
    set: (v: Record<string, string>) => void,
    disabled = false,
  ) => {
    const value =
      values[p.name] ?? (disabled && result ? result.used[p.name] : undefined) ?? p.default;
    const label = `${p.label}${p.unit ? ` (${p.unit})` : ""}`;
    return (
      <label key={p.name} title={p.help}>
        {label}
        {p.type === "choice" ? (
          <select
            value={value}
            disabled={disabled}
            onChange={(e) => set({ ...values, [p.name]: e.target.value })}
          >
            {p.choices.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ) : (
          <input
            value={value}
            disabled={disabled}
            onChange={(e) => set({ ...values, [p.name]: e.target.value })}
          />
        )}
      </label>
    );
  };

  // parameters that the catalogue part replaces: shown with its values, not editable
  const fromPart = (name: string) =>
    !!partId && !!result && result.used[name] !== undefined && params[name] === undefined;

  return (
    <main className="two-col">
      <section className="panel editor">
        {selector}
        <h2>Bancada: sensores, atuadores e placas</h2>
        <p className="small muted">
          As peças da biblioteca do simulador, com o mesmo modelo do esquemático, em ensaios de
          laboratório no ngspice (as placas e o CLP rodam um programa de ensaio na co-simulação).
          Cada medida é comparada com a equação que o modelo implementa.
        </p>
        <label>
          Peça da biblioteca
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {grouped.map(([g, list]) => (
              <optgroup key={g} label={g}>
                {list.map((b) => (
                  <option key={b.kind} value={b.kind}>
                    {b.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        {info && (
          <>
            <p className="small">{info.description}</p>
            <p className="small muted">
              <strong>Ensaio:</strong> {info.summary} <strong>Mede:</strong> {info.tests.join("; ")}
              .
            </p>
            {parts.length > 0 && (
              <label>
                Usar o datasheet de
                <select value={partId} onChange={(e) => setPartId(e.target.value)}>
                  <option value="">nenhum (valores abaixo)</option>
                  {parts.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.part_number} ({d.manufacturer})
                      {d.status !== "revisado" ? " — não revisado" : ""}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <h3>Condições do ensaio</h3>
            {info.fixture.map((p) => field(p, fixture, setFixture))}
            {info.params.length > 0 && <h3>Modelo</h3>}
            {info.params.map((p) => field(p, params, setParams, fromPart(p.name)))}
            <button className="primary" onClick={() => run()} disabled={busy}>
              {busy ? "Rodando…" : "Rodar os ensaios"}
            </button>
            {info.seconds > 5 && (
              <p className="small muted">Leva cerca de {Math.round(info.seconds)} s.</p>
            )}
          </>
        )}
        {result && (
          <details>
            <summary>Netlists dos ensaios</summary>
            {Object.entries(result.netlists).map(([k, n]) => (
              <div key={k}>
                <h4>{k}</h4>
                <pre className="small">{n}</pre>
              </div>
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
        {result && result.kind === kind && (
          <>
            <h3>Ensaios</h3>
            <table className="params">
              <thead>
                <tr>
                  <th>Ensaio</th>
                  <th>Simulado</th>
                  <th>Analítico</th>
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
            {result.warnings.map((w) => (
              <p key={w} className="small note">
                {w}
              </p>
            ))}
            {result.curves.map((c) => (
              <div key={c.id}>
                <h3>{c.title}</h3>
                <SignalPlot
                  x={c.x}
                  xUnit={c.x_unit}
                  xLabel={c.x_label}
                  xLog={c.x_log}
                  traces={c.traces.map((t) => ({
                    ...t,
                    points: t.values.filter((v) => v !== null).length < 10,
                  }))}
                  height={240}
                />
              </div>
            ))}
            <h3>Memória de cálculo</h3>
            <CalcSteps steps={result.steps} />
          </>
        )}
      </section>
    </main>
  );
}
