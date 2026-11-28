import { useEffect, useMemo, useRef, useState } from "react";
import {
  design,
  type CandidateOut,
  type CircuitElement,
  type DesignIn,
  type DesignOut,
  type PowerMeasure,
  type Quantity,
  type SimulateOut,
  type UserProbe,
  type WaveMeasure,
} from "../../api";
import { COLORS, SignalPlot, type Trace } from "../../components/SignalPlot";
import { formatEng } from "../../format";
import { matchElement, probeText, sameProbe } from "./circuitMatch";
import { resample, resampleLog, tracePeriod } from "./specForm";
import { PartSelect } from "./PartSelect";
import "./design-analysis.css";

function fmt(q: Quantity | null | undefined, digits = 4): string {
  if (!q) return "—";
  if (q.unit === "" || q.unit === "dimensionless") return q.value.toFixed(3).replace(".", ",");
  return formatEng(q.value, q.unit, digits);
}

/** Numerical noise of the simulation (1e-15 of the peak) shown as zero. */
function clean(q: Quantity, ref: number): Quantity {
  return Math.abs(q.value) < 1e-6 * Math.abs(ref) ? { ...q, value: 0 } : q;
}

// ------------------------------------------------------------------------- results (ngspice)

/** Voltages, currents and powers measured on the ngspice run of the circuit. */
export function SimResults({
  sim,
  busy,
  error,
}: {
  sim: SimulateOut | null;
  busy: boolean;
  error: string | null;
}) {
  const m = sim?.measurements;
  const volts = (m?.waves ?? []).filter((w) => w.unit === "V");
  const amps = (m?.waves ?? []).filter((w) => w.unit === "A");
  return (
    <section className="sim-results" aria-label="Resultados da simulação">
      <h3 className="plot-title">
        Grandezas do circuito simulado (ngspice){" "}
        <span className="muted small">{busy ? "simulando…" : ""}</span>
      </h3>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {sim?.edited && (
        <p className="note small">
          Valores alterados no esquemático: estas grandezas são do circuito editado; o cálculo
          analítico abaixo continua descrevendo o projeto original.
        </p>
      )}
      {!m && !busy && !error && (
        <p className="muted small">Este circuito não tem simulação no tempo para medir.</p>
      )}
      {volts.length > 0 && <WaveTable title="Tensões" rows={volts} />}
      {amps.length > 0 && <WaveTable title="Correntes" rows={amps} />}
      {m && m.powers.length > 0 && <PowerTable rows={m.powers} />}
      {m && (
        <p className="muted small">
          Valores no último período da simulação em regime. Pico = máximo de |x|; médio = (1/T)∫x
          dt; eficaz (rms) = √((1/T)∫x² dt). P = (1/T)∫v·i dt; S = V<sub>ef</sub>·I
          <sub>ef</sub>; Q = V₁·I₁·sen φ₁ (fundamental); D = √(S² − P² − Q²) (distorção); FP = P/S;
          cos φ₁ = fator de deslocamento (IEEE Std 1459-2010).
        </p>
      )}
    </section>
  );
}

function WaveTable({ title, rows }: { title: string; rows: WaveMeasure[] }) {
  return (
    <table className="results sim-table">
      <thead>
        <tr>
          <th>{title}</th>
          <th>Pico</th>
          <th>Médio</th>
          <th>Eficaz (rms)</th>
          <th>Mínimo</th>
          <th>Máximo</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((w) => (
          <tr key={w.label}>
            <td>{w.label}</td>
            <td className="num">{fmt(w.peak)}</td>
            <td className="num">{fmt(clean(w.avg, w.peak.value))}</td>
            <td className="num">{fmt(w.rms)}</td>
            <td className="num">{fmt(clean(w.min, w.peak.value))}</td>
            <td className="num">{fmt(clean(w.max, w.peak.value))}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PowerTable({ rows }: { rows: PowerMeasure[] }) {
  return (
    <table className="results sim-table">
      <thead>
        <tr>
          <th>Potências</th>
          <th>V eficaz</th>
          <th>I eficaz</th>
          <th>Aparente S</th>
          <th>Ativa P</th>
          <th>Reativa Q</th>
          <th>Distorção D</th>
          <th>FP</th>
          <th>cos φ₁</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.label}>
            <td>{p.label}</td>
            <td className="num">{fmt(p.V_rms)}</td>
            <td className="num">{fmt(p.I_rms)}</td>
            <td className="num">{fmt(p.S)}</td>
            <td className="num">{fmt(clean(p.P, p.S.value))}</td>
            <td className="num">{fmt(clean(p.Q, p.S.value))}</td>
            <td className="num">{fmt(clean(p.D, p.S.value))}</td>
            <td className="num">{fmt(p.PF)}</td>
            <td className="num">{fmt(p.DPF)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ------------------------------------------------------------------------- waveforms

const MARK = { avg: "#d99a00", rms: "#2fa36b", peak: "#c2417e" };

function stats(values: number[]): { avg: number; rms: number; peakIdx: number } {
  let s = 0;
  let s2 = 0;
  let peakIdx = 0;
  values.forEach((v, i) => {
    s += v;
    s2 += v * v;
    if (Math.abs(v) > Math.abs(values[peakIdx] ?? 0)) peakIdx = i;
  });
  const n = Math.max(values.length, 1);
  return { avg: s / n, rms: Math.sqrt(s2 / n), peakIdx };
}

/** Mean and RMS lines and the peak point of a trace, coloured apart from the traces. */
export function markerTraces(
  values: number[],
  unit: string,
  measured: WaveMeasure | undefined,
): Trace[] {
  if (values.length === 0) return [];
  const st = stats(values);
  const peakAbs = Math.abs(values[st.peakIdx] ?? 0);
  const rawAvg = measured?.avg.value ?? st.avg;
  const avg = Math.abs(rawAvg) < 1e-6 * peakAbs ? 0 : rawAvg;
  const rms = measured?.rms.value ?? st.rms;
  const peak = values[st.peakIdx] ?? 0;
  const point: (number | null)[] = values.map(() => null);
  point[st.peakIdx] = peak;
  return [
    {
      name: `médio = ${formatEng(avg, unit, 4)}`,
      unit,
      values: values.map(() => avg),
      dash: [10, 5],
      color: MARK.avg,
    },
    {
      name: `eficaz = ${formatEng(rms, unit, 4)}`,
      unit,
      values: values.map(() => rms),
      dash: [2, 4],
      width: 2,
      color: MARK.rms,
    },
    {
      name: `pico = ${formatEng(measured?.peak.value ?? Math.abs(peak), unit, 4)}`,
      unit,
      values: point,
      points: true,
      color: MARK.peak,
    },
  ];
}

export function Waves({
  out,
  sim,
  simBusy,
  onSimulate,
  frequency,
}: {
  out: DesignOut;
  sim: SimulateOut | null;
  simBusy: boolean;
  onSimulate: () => void;
  frequency: Quantity | undefined;
}) {
  const [marks, setMarks] = useState(true);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const period = tracePeriod(out.result.trace_period, frequency);
  const measured = useMemo(
    () => new Map((sim?.measurements?.waves ?? []).map((w) => [w.label, w])),
    [sim],
  );
  const groups = useMemo(() => {
    const out_: { label: string; x: number[]; traces: Trace[] }[] = [];
    for (const [label, tr] of Object.entries(out.result.traces)) {
      const n = tr.values.length;
      const x = Array.from({ length: n }, (_, k) => (k / n) * period);
      const traces: Trace[] = [
        { name: `${label} (cálculo)`, unit: tr.unit, values: tr.values, color: COLORS[0] },
      ];
      const s = sim?.traces[label];
      let ref = tr.values;
      if (sim && s) {
        ref = resample(
          sim.t_ms.map((t) => t / 1e3),
          s.values,
          x,
        );
        traces.push({
          name: `${label} (ngspice)`,
          unit: tr.unit,
          dash: [6, 4],
          values: ref,
          color: COLORS[1],
        });
      }
      if (marks)
        traces.push(...markerTraces(ref, tr.unit, sim && s ? measured.get(label) : undefined));
      out_.push({ label, x, traces });
    }
    // waveforms only the simulation has (primary, devices, probes added on the schematic)
    if (sim && sim.t_ms.length > 0) {
      const x = sim.t_ms.map((t) => t / 1e3);
      for (const [label, s] of Object.entries(sim.traces)) {
        if (label in out.result.traces) continue;
        const traces: Trace[] = [
          { name: `${label} (ngspice)`, unit: s.unit, values: s.values, color: COLORS[1] },
        ];
        if (marks) traces.push(...markerTraces(s.values, s.unit, measured.get(label)));
        out_.push({ label, x, traces });
      }
    }
    return out_;
  }, [out, sim, period, marks, measured]);
  const bode = useMemo(() => {
    const f = out.result.bode_f?.values;
    if (!f || f.length === 0) return null;
    const traces: Trace[] = [];
    for (const [label, tr] of Object.entries(out.result.bode ?? {})) {
      traces.push({ name: `${label} (cálculo)`, unit: tr.unit, values: tr.values });
      const s = sim?.bode?.[label];
      if (sim?.bode_f && sim.bode_f.length > 1 && s) {
        traces.push({
          name: `${label} (ngspice .ac)`,
          unit: tr.unit,
          dash: [6, 4],
          values: resampleLog(sim.bode_f, s.values, f),
        });
      }
    }
    return { f, traces };
  }, [out, sim]);
  const toggle = (label: string) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });

  return (
    <>
      <div className="row wrap">
        <button onClick={onSimulate} disabled={simBusy}>
          {simBusy ? "Simulando…" : sim ? "Simular de novo" : "Conferir com o ngspice"}
        </button>
        {sim && (
          <span className={sim.ok ? "status-ok" : "status-violado"}>
            {sim.ok
              ? "Cálculo e simulação concordam dentro das tolerâncias."
              : sim.edited
                ? "Circuito editado no esquemático: a simulação difere do cálculo do projeto."
                : "Divergência acima da tolerância: veja a tabela."}
          </span>
        )}
        <span className="grow" />
        <label className="inline small">
          <input type="checkbox" checked={marks} onChange={(e) => setMarks(e.target.checked)} />{" "}
          Marcar médio, eficaz e pico
        </label>
      </div>
      {sim && (
        <table className="results">
          <thead>
            <tr>
              <th>Grandeza</th>
              <th>Cálculo</th>
              <th>ngspice</th>
              <th>Erro</th>
              <th>Tolerância</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sim.comparisons.map((c) => (
              <tr key={c.quantity}>
                <td>{c.quantity}</td>
                <td className="num">{fmt(c.analytic, 4)}</td>
                <td className="num">{fmt(c.simulated, 4)}</td>
                <td className="num">{c.error_pct.toFixed(2).replace(".", ",")} %</td>
                <td className="num">{c.tolerance_pct.toFixed(1).replace(".", ",")} %</td>
                <td className={c.ok ? "status-ok" : "status-violado"}>
                  {c.ok ? "confere" : "diverge"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {groups.length === 0 && !bode && (
        <p className="muted">
          Este circuito é de corrente contínua: não há forma de onda a mostrar. A simulação confere
          os valores do ponto de operação na tabela acima.
        </p>
      )}
      {groups.length > 0 && (
        <div className="wave-picker" role="group" aria-label="Formas de onda exibidas">
          {groups.map((g) => (
            <label key={g.label} className="inline small">
              <input
                type="checkbox"
                checked={!hidden.has(g.label)}
                onChange={() => toggle(g.label)}
              />{" "}
              {g.label}
            </label>
          ))}
        </div>
      )}
      {bode && (
        <div>
          <h3 className="plot-title">Resposta em frequência (|H|)</h3>
          <SignalPlot
            x={bode.f}
            xUnit="Hz"
            xLabel="f"
            xLog
            yLog
            traces={bode.traces}
            height={260}
          />
        </div>
      )}
      {groups
        .filter((g) => !hidden.has(g.label))
        .map((g) => (
          <div key={g.label}>
            <h3 className="plot-title">{g.label}</h3>
            <SignalPlot x={g.x} xUnit="s" xLabel="t" traces={g.traces} height={220} />
          </div>
        ))}
      <p className="muted small">
        Para ver outra grandeza (tensão em um nó, tensão diferencial, corrente ou potência de um
        componente), clique no componente na aba Esquemático.
      </p>
    </>
  );
}

// ------------------------------------------------------------------------- schematic

/**
 * Drawing of the circuit whose labels open the element: edit its value, swap its catalogue
 * part (model) and add waveforms of its voltage, current or power.
 */
export function CircuitView({
  moduleId,
  body,
  svg,
  options,
  locks,
  onLock,
  overrides,
  onOverrides,
  probes,
  onProbes,
}: {
  moduleId: string;
  body: DesignIn;
  svg: string;
  options: Record<string, CandidateOut[]>;
  locks: Record<string, string>;
  onLock: (designator: string, id: string) => void;
  overrides: Record<string, string>;
  onOverrides: (o: Record<string, string>) => void;
  probes: UserProbe[];
  onProbes: (p: UserProbe[]) => void;
}) {
  const [elements, setElements] = useState<CircuitElement[]>([]);
  const [nodes, setNodes] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [na, setNa] = useState("");
  const [nb, setNb] = useState("0");
  const drawing = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    design
      .elements(moduleId, body)
      .then((r) => {
        if (!alive) return;
        setElements(r.elements);
        setNodes(r.nodes);
        setError(null);
      })
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [moduleId, body]);

  // labels of the drawing that name an element become clickable
  useEffect(() => {
    const root = drawing.current;
    if (!root) return;
    root.querySelectorAll("text").forEach((t) => {
      const el = matchElement(t.textContent ?? "", elements);
      if (el) {
        t.setAttribute("data-el", el.name);
        t.classList.add("sch-hit");
        t.classList.toggle("sch-selected", el.name === selected);
        if (!t.querySelector("title")) {
          const tip = document.createElementNS("http://www.w3.org/2000/svg", "title");
          tip.textContent = `${el.name}: clique para editar ou medir`;
          t.appendChild(tip);
        }
      }
    });
  }, [svg, elements, selected]);

  const el = elements.find((e) => e.name === selected) ?? null;
  const add = (p: UserProbe) => {
    if (!probes.some((q) => sameProbe(q, p))) onProbes([...probes, p]);
  };
  const real = elements.filter((e) => !e.sense);

  return (
    <div className="circuit-view">
      <div className="circuit-drawing">
        <div
          ref={drawing}
          className="schematic"
          onClick={(e) => {
            const hit = (e.target as Element).closest("[data-el]");
            if (hit) setSelected(hit.getAttribute("data-el"));
          }}
          // The SVG comes from our own backend (escaped labels), not from user HTML.
          dangerouslySetInnerHTML={{ __html: svg }}
        />
        <p className="muted small">
          Clique em um componente do desenho (ou na lista abaixo) para alterar o valor, trocar o
          modelo ou pedir a forma de onda de tensão, corrente ou potência.
        </p>
        <div className="element-chips" role="list" aria-label="Componentes do circuito simulado">
          {real.map((e) => (
            <button
              key={e.name}
              role="listitem"
              className={`secondary chip${e.name === selected ? " active" : ""}${
                e.name in overrides ? " edited" : ""
              }`}
              onClick={() => setSelected(e.name)}
            >
              {e.name}
            </button>
          ))}
        </div>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
      </div>
      <aside className="element-panel" aria-label="Componente selecionado">
        {el ? (
          <ElementPanel
            key={el.name}
            el={el}
            options={el.role ? (options[el.role] ?? []) : []}
            lock={el.role ? (locks[el.role] ?? "") : ""}
            onLock={(id) => el.role && onLock(el.role, id)}
            override={overrides[el.name]}
            onValue={(v) => {
              const next = { ...overrides };
              if (v === null) delete next[el.name];
              else next[el.name] = v;
              onOverrides(next);
            }}
            onProbe={add}
          />
        ) : (
          <p className="muted small">Nenhum componente selecionado.</p>
        )}
        <h4>Tensão diferencial entre dois nós</h4>
        <div className="row wrap">
          <select aria-label="Nó positivo" value={na} onChange={(e) => setNa(e.target.value)}>
            <option value="">nó +</option>
            {nodes.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <select aria-label="Nó negativo" value={nb} onChange={(e) => setNb(e.target.value)}>
            {["0", ...nodes.filter((n) => n !== "0")].map((n) => (
              <option key={n} value={n}>
                {n === "0" ? "0 (terra)" : n}
              </option>
            ))}
          </select>
          <button
            className="secondary"
            disabled={!na || na === nb}
            onClick={() => add(nb === "0" ? { kind: "v", a: na } : { kind: "vdiff", a: na, b: nb })}
          >
            Adicionar
          </button>
        </div>
        <h4>Formas de onda adicionadas</h4>
        {probes.length === 0 ? (
          <p className="muted small">Nenhuma. Elas aparecem em Formas de onda e em Resultados.</p>
        ) : (
          <ul className="probe-list">
            {probes.map((p, i) => (
              <li key={i}>
                {probeText(p, elements)}{" "}
                <button
                  className="link"
                  aria-label={`Retirar ${probeText(p, elements)}`}
                  onClick={() => onProbes(probes.filter((_, k) => k !== i))}
                >
                  retirar
                </button>
              </li>
            ))}
          </ul>
        )}
        {Object.keys(overrides).length > 0 && (
          <div className="row">
            <button className="secondary" onClick={() => onOverrides({})}>
              Restaurar todos os valores do projeto
            </button>
          </div>
        )}
      </aside>
    </div>
  );
}

function ElementPanel({
  el,
  options,
  lock,
  onLock,
  override,
  onValue,
  onProbe,
}: {
  el: CircuitElement;
  options: CandidateOut[];
  lock: string;
  onLock: (id: string) => void;
  override: string | undefined;
  onValue: (v: string | null) => void;
  onProbe: (p: UserProbe) => void;
}) {
  const [draft, setDraft] = useState(override ?? el.value);
  const two = el.nodes.length >= 2;
  return (
    <div>
      <h4>
        {el.name} <span className="muted small">nós {el.nodes.join(", ")}</span>
      </h4>
      {el.edit !== "none" && (
        <label>
          {el.edit === "value" ? "Valor (SPICE: 4.7k, 100u, 2.2m…)" : "Descrição da fonte (SPICE)"}
          <span className="row">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onValue(draft)}
            />
            <button className="secondary" onClick={() => onValue(draft)}>
              Aplicar
            </button>
          </span>
        </label>
      )}
      {override !== undefined && (
        <p className="small">
          Alterado no esquemático (projeto: {el.original ?? "—"}).{" "}
          <button className="link" onClick={() => onValue(null)}>
            Restaurar
          </button>
        </p>
      )}
      {el.role && (
        <label>
          Modelo (qualquer componente da família no catálogo)
          <PartSelect options={options} value={lock} onChange={onLock} />
        </label>
      )}
      {el.edit === "none" && !el.role && (
        <p className="muted small">Elemento de modelo da simulação: sem valor editável.</p>
      )}
      <div className="row wrap probe-buttons">
        {two && (
          <button
            className="secondary"
            onClick={() =>
              onProbe(
                el.nodes[1] === "0"
                  ? { kind: "v", a: el.nodes[0] ?? "" }
                  : { kind: "vdiff", a: el.nodes[0] ?? "", b: el.nodes[1] ?? "" },
              )
            }
          >
            Tensão nos terminais
          </button>
        )}
        {el.nodes.length > 2
          ? el.pins.map((pin, k) => (
              <button
                key={pin}
                className="secondary"
                onClick={() => onProbe({ kind: "i", a: el.name, pin: k })}
              >
                Corrente ({pin})
              </button>
            ))
          : two && (
              <button className="secondary" onClick={() => onProbe({ kind: "i", a: el.name })}>
                Corrente
              </button>
            )}
        {two && (
          <button className="secondary" onClick={() => onProbe({ kind: "p", a: el.name })}>
            Potência
          </button>
        )}
        {el.nodes
          .filter((n) => n !== "0")
          .map((n) => (
            <button key={n} className="secondary" onClick={() => onProbe({ kind: "v", a: n })}>
              Tensão do nó {n}
            </button>
          ))}
      </div>
    </div>
  );
}
