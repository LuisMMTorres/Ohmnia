import { useEffect, useMemo, useRef, useState } from "react";
import {
  design,
  type DesignIn,
  type DesignModuleInfo,
  type DesignOut,
  type MarginStatus,
  type Policy,
  type ProjectDocument,
  type Quantity,
  type SimulateOut,
} from "../api";
import { CalcSteps } from "../components/CalcSteps";
import { SignalPlot, type Trace } from "../components/SignalPlot";
import { formatEng, unitSymbol } from "../format";
import { BomTab } from "./design/BomTab";
import { BreadboardTab } from "./design/BreadboardTab";
import { ProjectBar } from "./design/ProjectBar";
import {
  type Field,
  fieldsFromSchema,
  isQuantity,
  resample,
  resampleLog,
  sliderRange,
  sliderStep,
  tracePeriod,
  visible,
} from "./design/specForm";

type Tab =
  | "resultados"
  | "componentes"
  | "materiais"
  | "ondas"
  | "esquematico"
  | "protoboard"
  | "memoria";
const TABS: [Tab, string][] = [
  ["resultados", "Resultados"],
  ["componentes", "Componentes e margens"],
  ["materiais", "Lista de materiais"],
  ["ondas", "Formas de onda"],
  ["esquematico", "Esquemático"],
  ["protoboard", "Protoboard"],
  ["memoria", "Memória de cálculo"],
];
const STATUS: Record<MarginStatus, string> = { ok: "ok", atencao: "atenção", violado: "violado" };

function fmt(q: Quantity | null | undefined, digits = 3): string {
  if (!q) return "—";
  if (q.unit === "%") return `${Number(q.value.toPrecision(digits))}`.replace(".", ",") + " %";
  return formatEng(q.value, q.unit, digits);
}

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Design of a topology: spec → calculation → real parts → margins → simulation check. */
export function DesignPage() {
  const [modules, setModules] = useState<DesignModuleInfo[]>([]);
  const [moduleId, setModuleId] = useState("");
  const [spec, setSpec] = useState<Record<string, unknown>>({});
  const [policy, setPolicy] = useState<Policy>("didatico");
  const [locks, setLocks] = useState<Record<string, string>>({});
  const [out, setOut] = useState<DesignOut | null>(null);
  const [svg, setSvg] = useState("");
  const [sim, setSim] = useState<SimulateOut | null>(null);
  const [simBusy, setSimBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("resultados");
  const [costs, setCosts] = useState<Record<string, number>>({});
  const [project, setProject] = useState<ProjectDocument | null>(null);
  const latest = useRef(0);

  useEffect(() => {
    design
      .modules()
      .then((m) => {
        setModules(m);
        const first = m[0];
        if (first) {
          setModuleId(first.id);
          setSpec(first.defaults);
        }
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const info = modules.find((m) => m.id === moduleId);
  const fields = useMemo(
    () => (info ? fieldsFromSchema(info.json_schema, info.defaults) : []),
    [info],
  );
  const body: DesignIn = useMemo(() => ({ spec, policy, locks }), [spec, policy, locks]);
  // exports also carry the BOM costs and the project name (they do not change the design)
  const exportBody: DesignIn = { ...body, costs, project: project?.name ?? null };

  // Re-run the design (debounced) whenever an input changes; the simulation must be re-run.
  useEffect(() => {
    if (!moduleId) return;
    const id = ++latest.current;
    setSim(null);
    const timer = window.setTimeout(() => {
      setBusy(true);
      Promise.all([
        design.run(moduleId, body),
        design.schematic(moduleId, body).then((b) => b.text()),
      ])
        .then(([o, s]) => {
          if (id !== latest.current) return;
          setOut(o);
          setSvg(s);
          setError(null);
        })
        .catch((e: Error) => id === latest.current && setError(e.message))
        .finally(() => id === latest.current && setBusy(false));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [moduleId, body]);

  const chooseModule = (id: string) => {
    const m = modules.find((x) => x.id === id);
    if (!m) return;
    setModuleId(id);
    setSpec(m.defaults);
    setLocks({});
    setCosts({});
    setOut(null);
    setSvg("");
  };

  const runSim = () => {
    const id = latest.current;
    setSimBusy(true);
    design
      .simulate(moduleId, body)
      .then((s) => id === latest.current && setSim(s))
      .catch((e: Error) => setError(e.message))
      .finally(() => setSimBusy(false));
  };

  const openProject = (doc: ProjectDocument) => {
    setModuleId(doc.module_id);
    setSpec(doc.current.spec);
    setPolicy(doc.current.policy);
    setLocks(doc.current.locks);
    setCosts(doc.current.costs);
    setSim(null);
  };

  type Export =
    | "report-html"
    | "report-pdf"
    | "bom-csv"
    | "bom-xlsx"
    | "bom-pdf"
    | "netlist"
    | "kicad";
  const download = (kind: Export) => {
    if (!kind) return;
    const base = project ? project.name.replace(/[^\p{L}\p{N}-]+/gu, "-") : moduleId;
    if (kind === "netlist") {
      if (out) saveBlob(new Blob([out.netlist], { type: "text/plain" }), `${base}.cir`);
      return;
    }
    const jobs: Record<Exclude<Export, "netlist">, [() => Promise<Blob>, string]> = {
      "report-html": [() => design.report(moduleId, exportBody, true), `${base}-relatorio.html`],
      "report-pdf": [() => design.reportPdf(moduleId, exportBody, true), `${base}-relatorio.pdf`],
      "bom-csv": [() => design.bomFile(moduleId, exportBody, "csv"), `${base}-materiais.csv`],
      "bom-xlsx": [() => design.bomFile(moduleId, exportBody, "xlsx"), `${base}-materiais.xlsx`],
      "bom-pdf": [() => design.bomFile(moduleId, exportBody, "pdf"), `${base}-materiais.pdf`],
      kicad: [() => design.kicad(moduleId, exportBody), `${base}.net`],
    };
    const [fn, name] = jobs[kind];
    setExporting(true);
    fn()
      .then((b) => saveBlob(b, name))
      .catch((e: Error) => setError(e.message))
      .finally(() => setExporting(false));
  };
  const [exporting, setExporting] = useState(false);

  const setField = (key: string, value: unknown) => setSpec((s) => ({ ...s, [key]: value }));

  return (
    <main>
      <section className="panel editor" aria-label="Especificação">
        <label>
          Módulo de projeto
          <select value={moduleId} onChange={(e) => chooseModule(e.target.value)}>
            {modules.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id} · {m.title}
              </option>
            ))}
          </select>
        </label>
        {info &&
          fields
            .filter((f) => visible(moduleId, f.key, spec))
            .map((f) => (
              <SpecField
                key={f.key}
                field={f}
                label={info.spec_labels[f.key] ?? f.key}
                enumLabels={info.enum_labels}
                value={spec[f.key]}
                def={info.defaults[f.key]}
                onChange={(v) => setField(f.key, v)}
              />
            ))}
        <label>
          Critério de derating
          <select value={policy} onChange={(e) => setPolicy(e.target.value as Policy)}>
            <option value="didatico">didático</option>
            <option value="industrial">industrial</option>
          </select>
        </label>
        <p className="muted small">
          Critérios de projeto, não normativos. Os controles deslizantes refazem o projeto a cada
          mudança, para explorar os limites da topologia.
        </p>
        <div className="row">
          <button className="secondary" onClick={() => info && chooseModule(info.id)}>
            Valores padrão
          </button>
        </div>
      </section>

      <section className="panel" aria-label="Projeto">
        <ProjectBar
          state={{ moduleId, spec, policy, locks, costs }}
          project={project}
          onProject={setProject}
          onOpen={openProject}
          onError={setError}
        />
        <div className="row design-head">
          <strong>{info?.title}</strong>
          <span className="muted small">{busy ? "calculando…" : out ? "atualizado" : ""}</span>
          <span className="grow" />
          {exporting && <span className="muted small">gerando…</span>}
          <select
            aria-label="Exportar"
            value=""
            disabled={!out || exporting}
            onChange={(e) => download(e.target.value as Export)}
          >
            <option value="">Exportar…</option>
            <option value="report-pdf">Relatório (PDF)</option>
            <option value="report-html">Relatório (HTML, imprimível)</option>
            <option value="bom-xlsx">Lista de materiais (XLSX)</option>
            <option value="bom-pdf">Lista de materiais (PDF)</option>
            <option value="bom-csv">Lista de materiais (CSV)</option>
            <option value="netlist">Netlist SPICE</option>
            <option value="kicad">Netlist KiCad (.net)</option>
          </select>
        </div>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {out && out.result.warnings.length > 0 && (
          <ul className="warnings">
            {out.result.warnings.map((w, i) => (
              <li key={i} className={`warn-${w.code}`}>
                {w.message}
              </li>
            ))}
          </ul>
        )}
        <nav className="tabs" aria-label="Partes do projeto">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              className={key === tab ? "tab active" : "tab"}
              aria-current={key === tab ? "page" : undefined}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </nav>
        {out && info && tab === "resultados" && <Summary out={out} labels={info.summary_labels} />}
        {out && tab === "componentes" && (
          <Components
            out={out}
            locks={locks}
            onLock={(d, id) =>
              setLocks((l) => {
                const next = { ...l };
                if (id) next[d] = id;
                else delete next[d];
                return next;
              })
            }
          />
        )}
        {out && tab === "materiais" && (
          <BomTab moduleId={moduleId} body={body} costs={costs} onCosts={setCosts} version={out} />
        )}
        {out && tab === "ondas" && (
          <Waves
            out={out}
            sim={sim}
            simBusy={simBusy}
            onSimulate={runSim}
            frequency={spec.f as Quantity | undefined}
          />
        )}
        {tab === "esquematico" && (
          // The SVG comes from our own backend (escaped labels), not from user HTML.
          <div className="schematic" dangerouslySetInnerHTML={{ __html: svg }} />
        )}
        {out && tab === "protoboard" && (
          <BreadboardTab moduleId={moduleId} body={body} version={out} />
        )}
        {out && tab === "memoria" && <CalcSteps steps={out.result.steps} />}
      </section>
    </main>
  );
}

function SpecField({
  field,
  label,
  enumLabels,
  value,
  def,
  onChange,
}: {
  field: Field;
  label: string;
  enumLabels: Record<string, string>;
  value: unknown;
  def: unknown;
  onChange: (v: unknown) => void;
}) {
  if (field.kind === "enum") {
    return (
      <label>
        {label}
        <select
          value={String(value)}
          onChange={(e) => {
            const raw = e.target.value;
            onChange(typeof field.options[0] === "number" ? Number(raw) : raw);
          }}
        >
          {field.options.map((o) => (
            <option key={String(o)} value={String(o)}>
              {enumLabels[String(o)] ?? String(o)}
            </option>
          ))}
        </select>
      </label>
    );
  }
  if (field.kind === "bool") {
    return (
      <label className="inline">
        <input
          type="checkbox"
          checked={value === true}
          onChange={(e) => onChange(e.target.checked)}
        />{" "}
        {label}
      </label>
    );
  }
  const q = field.kind === "quantity";
  const num = q ? (isQuantity(value) ? value.value : 0) : Number(value);
  const defNum = q ? (isQuantity(def) ? def.value : 1) : Number(def);
  const [lo, hi] = sliderRange(field, defNum);
  const set = (n: number) => {
    if (Number.isNaN(n)) return;
    onChange(q ? { value: n, unit: field.unit } : n);
  };
  return (
    <label className="spec-num">
      <span>
        {label}
        {q && field.unit ? ` (${unitSymbol(field.unit)})` : ""}
      </span>
      <span className="row">
        <input
          type="number"
          value={num}
          step="any"
          onChange={(e) => e.target.value !== "" && set(Number(e.target.value))}
        />
        <input
          type="range"
          aria-label={`${label}: ajuste rápido`}
          min={lo}
          max={hi}
          step={sliderStep(lo, hi)}
          value={Math.min(hi, Math.max(lo, num))}
          onChange={(e) => set(Number(e.target.value))}
        />
      </span>
    </label>
  );
}

function Summary({ out, labels }: { out: DesignOut; labels: Record<string, string> }) {
  const r = out.result;
  return (
    <>
      <table className="results">
        <tbody>
          {Object.entries(r.summary)
            .filter(([k]) => k in labels)
            .map(([k, q]) => (
              <tr key={k}>
                <td>{labels[k]}</td>
                <td className="num">{fmt(q)}</td>
              </tr>
            ))}
        </tbody>
      </table>
      <p className="muted small">
        {r.converged
          ? `Cálculo com dispositivos reais convergiu em ${r.iterations} iteração(ões).`
          : "O cálculo com dispositivos reais não convergiu; veja os avisos."}
      </p>
    </>
  );
}

function Components({
  out,
  locks,
  onLock,
}: {
  out: DesignOut;
  locks: Record<string, string>;
  onLock: (designator: string, id: string) => void;
}) {
  const r = out.result;
  return (
    <>
      <table className="results">
        <thead>
          <tr>
            <th>Posição</th>
            <th>Função</th>
            <th>Componente</th>
          </tr>
        </thead>
        <tbody>
          {r.roles.map((role) => {
            const chosen = r.selection.find((c) => c.designator === role.designator);
            const opts = out.options[role.designator] ?? [];
            return (
              <tr key={role.designator}>
                <td>{role.designator}</td>
                <td>{role.description}</td>
                <td>
                  <select
                    aria-label={`Componente de ${role.designator}`}
                    value={locks[role.designator] ?? ""}
                    onChange={(e) => onLock(role.designator, e.target.value)}
                  >
                    <option value="">
                      automático{chosen && !chosen.locked ? `: ${chosen.part_number}` : ""}
                    </option>
                    {opts.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.part_number} ({o.manufacturer}){o.released ? "" : " · não revisado"}
                      </option>
                    ))}
                  </select>
                  {chosen && !chosen.released && (
                    <span className="badge a_verificar">não revisado</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {r.margins.length > 0 && (
        <table className="results">
          <thead>
            <tr>
              <th>Posição</th>
              <th>Parâmetro</th>
              <th>Esforço</th>
              <th>Nominal</th>
              <th>Fator exigido</th>
              <th>Margem</th>
              <th>Situação</th>
            </tr>
          </thead>
          <tbody>
            {r.margins.map((m, i) => (
              <tr key={i}>
                <td>{m.designator}</td>
                <td>{m.parameter}</td>
                <td className="num">{fmt(m.stress)}</td>
                <td className="num">{fmt(m.rating)}</td>
                <td className="num">{m.required_factor.toFixed(2).replace(".", ",")}</td>
                <td className="num">{m.margin_pct.toFixed(0)} %</td>
                <td className={`status-${m.status}`}>{STATUS[m.status]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {r.thermal.length > 0 && (
        <table className="results">
          <thead>
            <tr>
              <th>Posição</th>
              <th>Perda</th>
              <th>Tj</th>
              <th>Tj máx.</th>
              <th>Caminho térmico</th>
              <th>Rθsa exigida</th>
              <th>Rθsa do dissipador</th>
              <th>Situação</th>
            </tr>
          </thead>
          <tbody>
            {r.thermal.map((t) => (
              <tr key={t.designator}>
                <td>{t.designator}</td>
                <td className="num">{fmt(t.power)}</td>
                <td className="num">{fmt(t.Tj)}</td>
                <td className="num">{fmt(t.Tj_max)}</td>
                <td>{t.path}</td>
                <td className="num">
                  {t.required_Rsa && t.required_Rsa.value > 0 ? `≤ ${fmt(t.required_Rsa)}` : "—"}
                </td>
                <td className="num">{t.heatsink_Rsa ? `≈ ${fmt(t.heatsink_Rsa)}` : "—"}</td>
                <td className={`status-${t.status}`}>{STATUS[t.status]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function Waves({
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
  const period = tracePeriod(out.result.trace_period, frequency);
  const groups = useMemo(() => {
    const entries = Object.entries(out.result.traces);
    return entries.map(([label, tr]) => {
      const n = tr.values.length;
      const x = Array.from({ length: n }, (_, k) => (k / n) * period);
      const traces: Trace[] = [{ name: `${label} (cálculo)`, unit: tr.unit, values: tr.values }];
      const s = sim?.traces[label];
      if (sim && s) {
        traces.push({
          name: `${label} (ngspice)`,
          unit: tr.unit,
          dash: [6, 4],
          values: resample(
            sim.t_ms.map((t) => t / 1e3),
            s.values,
            x,
          ),
        });
      }
      return { label, x, traces };
    });
  }, [out, sim, period]);
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

  return (
    <>
      <div className="row">
        <button onClick={onSimulate} disabled={simBusy}>
          {simBusy ? "Simulando…" : sim ? "Simular de novo" : "Conferir com o ngspice"}
        </button>
        {sim && (
          <span className={sim.ok ? "status-ok" : "status-violado"}>
            {sim.ok
              ? "Cálculo e simulação concordam dentro das tolerâncias."
              : "Divergência acima da tolerância: veja a tabela."}
          </span>
        )}
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
      {groups.map((g) => (
        <div key={g.label}>
          <h3 className="plot-title">{g.label}</h3>
          <SignalPlot x={g.x} xUnit="s" xLabel="t" traces={g.traces} height={220} />
        </div>
      ))}
    </>
  );
}
