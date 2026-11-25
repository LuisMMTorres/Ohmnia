/** Free simulator: schematic editor, analyses, sweeps and results (spec 4.2 and 4.3). */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  download,
  schematicApi,
  watchJob,
  api,
  breadboardApi,
  type DamageOut,
  type Job,
  type NetlistOut,
  type PartOut,
  type TranSuggestion,
} from "../api";
import { CalcSteps } from "../components/CalcSteps";
import { emptyBreadboard } from "../breadboard/types";
import { MOTOR_KINDS } from "../breadboard/DeviceFaces";
import type { Motion } from "../breadboard/DeviceFaces";
import type { PackageSpec, PartView } from "../breadboard/types";
import { SCHEMATIC_EXAMPLES } from "../schematic/examples";
import { ResultsView } from "../schematic/ResultsView";
import { SchematicEditor, type Selection, type Tool } from "../schematic/SchematicEditor";
import { TRACE_COLORS } from "../schematic/Scope";
import {
  emptySchematic,
  emptySweep,
  type Analysis,
  type AnalysisKind,
  type Component,
  type Library,
  type MeasureKind,
  type ParamDef,
  type Schematic,
  type SymbolDef,
} from "../schematic/types";
import { BreadboardView, PinoutSource } from "../breadboard/BreadboardView";
import { useBreadboardSpec, useResolved } from "../breadboard/hooks";
import { SourceControls } from "../schematic/SourceControls";
import { removeSources, pruneOrphanSupplyLabels } from "../breadboard/instruments";
import { disconnectScope, syncScopeProbes } from "../breadboard/scopeConnections";
import { BenchScope } from "../breadboard/BenchScope";
import { BenchSupply } from "../breadboard/BenchSupply";
import { InteractiveBench } from "../breadboard/InteractiveBench";
import type { PlotData } from "../api";
import { nextRef } from "../schematic/geometry";
import { autoWire } from "../schematic/editing";
import { glowFrom, glowText } from "../schematic/indicators";
import {
  MANUAL_SWITCH_KINDS,
  stateDefault,
  switchPosition,
  switchText,
  toggleSwitch,
} from "../schematic/switches";
import { damageByRef } from "../schematic/damage";
import { DamageAlert } from "../schematic/DamageAlert";
import type { Glow } from "../schematic/symbols";
import { PackagePreview } from "../breadboard/PackageArt";
import { ProgramEditor } from "../cosim/ProgramEditor";
import { FirmwareControls } from "../cosim/FirmwareControls";
import { SimulatorPage } from "./SimulatorPage";
import { upgradeSchematic } from "../schematic/migrate";
import { WorkspaceSteps, type WorkspaceStep } from "../components/WorkspaceSteps";

const STORAGE = "circuitos.schematic";

function loadSaved(): Schematic {
  try {
    const raw = localStorage.getItem(STORAGE);
    if (raw)
      return pruneOrphanSupplyLabels(
        upgradeSchematic({ ...emptySchematic(), ...(JSON.parse(raw) as Schematic) }),
      );
  } catch {
    /* storage unavailable */
  }
  return SCHEMATIC_EXAMPLES["Filtro RC passa-baixas"]!();
}

const STATE_LABEL: Record<Job["state"], string> = {
  queued: "Na fila",
  running: "Simulando",
  done: "Concluída",
  failed: "Falhou",
  cancelled: "Cancelada",
};

/**
 * Generic household lamps by their nameplate (V and W printed on the bulb). No 127 V
 * manufacturer sheet was reachable; these are typed ratings, not datasheet data: choose a
 * catalogue lamp for a real part.
 */
const NAMEPLATE_LAMPS: [string, string][] = [
  ["127", "40"],
  ["127", "60"],
  ["127", "100"],
  ["220", "40"],
  ["220", "60"],
  ["220", "100"],
];
/** Kinds left out of the palette (still accepted from imported netlists). */
const HIDDEN_KINDS = new Set(["subckt"]);

const EDIT_TOOLS: [Tool, string][] = [
  [{ kind: "select" }, "Selecionar"],
  [{ kind: "wire" }, "Fio (W)"],
  [{ kind: "label" }, "Rótulo de nó"],
  [{ kind: "probe", probe: "v" }, "Ponteira V"],
  [{ kind: "probe", probe: "vdiff" }, "Ponteira V diferencial"],
  [{ kind: "probe", probe: "i" }, "Ponteira I"],
  [{ kind: "probe", probe: "p" }, "Potência"],
];

export function SchematicPage() {
  const [mode, setMode] = useState<"schematic" | "netlist">("schematic");
  return (
    <>
      <div className="subtabs">
        <button
          className={mode === "schematic" ? "tab active" : "tab"}
          onClick={() => setMode("schematic")}
        >
          Esquemático
        </button>
        <button
          className={mode === "netlist" ? "tab active" : "tab"}
          onClick={() => setMode("netlist")}
        >
          Netlist (texto)
        </button>
      </div>
      {mode === "schematic" ? <SchematicWorkspace /> : <SimulatorPage />}
    </>
  );
}

export function SchematicWorkspace({
  initialDocument,
  onDocumentChange,
}: { initialDocument?: Schematic; onDocumentChange?: (s: Schematic) => void } = {}) {
  const [library, setLibrary] = useState<Library | null>(null);
  const [sch, setSch] = useState<Schematic>(() =>
    pruneOrphanSupplyLabels(initialDocument ?? loadSaved()),
  );
  const [past, setPast] = useState<Schematic[]>([]);
  const [future, setFuture] = useState<Schematic[]>([]);
  const [tool, setTool] = useState<Tool>({ kind: "select" });
  const [selection, setSelection] = useState<Selection>(null);
  const [simulatedCircuit, setSimulatedCircuit] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [liveActive, setLiveActive] = useState(false);
  const [liveMeter, setLiveMeter] = useState(false);
  const [liveData, setLiveData] = useState<PlotData | null>(null);
  const liveSupplyCurrents = useMemo(
    () =>
      Object.fromEntries(
        sch.components.flatMap((c) => {
          const value = liveData?.traces[`i(${c.ref.toLowerCase()})`]?.values.at(-1);
          return value === undefined ? [] : [[c.ref, value]];
        }),
      ),
    [sch.components, liveData],
  );
  const [netlist, setNetlist] = useState<NetlistOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [panel, setPanel] = useState<"analyses" | "sweep" | "params" | "netlist">("analyses");
  const [importText, setImportText] = useState<string | null>(null);
  const [view, setView] = useState<"esquematico" | "protoboard">(() =>
    !initialDocument && sessionStorage.getItem("circuitos.simulator.view") === "protoboard"
      ? "protoboard"
      : "esquematico",
  );
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [indicatorParts, setIndicatorParts] = useState<{ led: PartOut[]; lamp: PartOut[] }>({
    led: [],
    lamp: [],
  });
  const [glows, setGlows] = useState<Record<string, Glow>>({});
  const [damage, setDamage] = useState<DamageOut[]>([]);
  const [damageClosed, setDamageClosed] = useState(false);

  const [showNodeNames, setShowNodeNames] = useState(false);
  const [nodeMap, setNodeMap] = useState<Record<string, string[]>>({});
  const [nodeError, setNodeError] = useState<string | null>(null);
  const [resultProbes, setResultProbes] = useState<string[]>([]);
  // direction of rotation: last point of v(<ref>_w) of each motor in the transient result
  const [motion, setMotion] = useState<Record<string, Motion>>({});
  const motorRefs = sch.components
    .filter((c) => MOTOR_KINDS.has(c.kind))
    .map((c) => c.ref)
    .join(",");
  useEffect(() => {
    setMotion({});
    if (!job || job.state !== "done" || !motorRefs) return;
    const plot = job.plots?.find((p) => p.kind === "tran");
    if (!plot) return;
    const names = motorRefs
      .split(",")
      .map((r) => `v(${r.toLowerCase()}_w)`)
      .filter((n) => plot.vectors.some((v) => v.name === n));
    if (!names.length) return;
    let cancelled = false;
    api
      .plot(job.id, plot.name, names, "real", 200)
      .then((data) => {
        if (cancelled) return;
        const out: Record<string, Motion> = {};
        for (const ref of motorRefs.split(",")) {
          const v = data.traces[`v(${ref.toLowerCase()}_w)`]?.values;
          if (v?.length) out[ref] = { rpm: (v[v.length - 1]! * 60) / (2 * Math.PI) };
        }
        setMotion(out);
      })
      .catch(() => setMotion({}));
    return () => {
      cancelled = true;
    };
  }, [job, motorRefs]);
  useEffect(() => {
    setNodeMap({});
    setNodeError(null);
    if (!showNodeNames) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      schematicApi
        .netlist(sch)
        .then((nl) => {
          if (!cancelled) setNodeMap(nl.nets);
        })
        .catch((e: Error) => {
          if (!cancelled) setNodeError(`Nomes dos nós indisponíveis: ${e.message}`);
        });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [sch, showNodeNames]);
  const [activeStep, setActiveStep] = useState<WorkspaceStep>("circuit");
  const circuitRef = useRef<HTMLDivElement>(null);
  const analysisRef = useRef<HTMLElement>(null);
  const resultsRef = useRef<HTMLElement>(null);
  const activateStep = (step: WorkspaceStep) => setActiveStep(step);
  useEffect(() => {
    const section = { circuit: circuitRef, analysis: analysisRef, results: resultsRef }[activeStep]
      .current;
    section?.focus({ preventScroll: true });
  }, [activeStep]);
  const bbSpec = useBreadboardSpec();
  const { resolved } = useResolved(sch);
  const fileRef = useRef<HTMLInputElement>(null);
  const [cosimExamples, setCosimExamples] = useState<
    { name: string; description: string; schematic: Schematic }[]
  >([]);

  useEffect(() => {
    schematicApi
      .library()
      .then(setLibrary)
      .catch((e: Error) => setError(e.message));
    schematicApi
      .examples()
      .then(setCosimExamples)
      .catch(() => setCosimExamples([]));
    Promise.all([schematicApi.parts("led"), schematicApi.parts("lamp")])
      .then(([led, lamp]) => setIndicatorParts({ led, lamp }))
      .catch(() => setIndicatorParts({ led: [], lamp: [] }));
  }, []);
  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(t);
  }, [notice]);
  // LEDs and lamps glow with the current of the last simulation
  useEffect(() => {
    setGlows({});
    const inds = netlist?.indicators ?? {};
    if (!job || job.state !== "done" || !Object.keys(inds).length) return;
    const plot =
      job.plots?.find((p) => p.kind === "tran") ?? job.plots?.find((p) => p.kind === "op");
    if (!plot) return;
    const names = Object.values(inds)
      .map((i) => i.vector)
      .filter((n) => plot.vectors.some((v) => v.name === n));
    if (!names.length) return;
    let cancelled = false;
    api
      .plot(job.id, plot.name, names, "real", 2000)
      .then((data) => {
        if (cancelled) return;
        const out: Record<string, Glow> = {};
        for (const [ref, ind] of Object.entries(inds)) {
          const v = data.traces[ind.vector]?.values;
          const g = v ? glowFrom(ind, v) : null;
          if (g) out[ref] = g;
        }
        setGlows(out);
      })
      .catch(() => setGlows({}));
    return () => {
      cancelled = true;
    };
  }, [job, netlist]);
  // bench supplies: current each voltage source delivers at the end of the last simulation
  const [supplyCurrents, setSupplyCurrents] = useState<Record<string, number>>({});
  useEffect(() => {
    setSupplyCurrents({});
    const supplies = netlist?.supplies ?? {};
    if (!job || job.state !== "done" || !Object.keys(supplies).length) return;
    // same plot as the LED brightness, so the display and the LEDs agree
    const plot =
      job.plots?.find((p) => p.kind === "tran") ?? job.plots?.find((p) => p.kind === "op");
    if (!plot) return;
    const names = Object.values(supplies).filter((n) => plot.vectors.some((v) => v.name === n));
    if (!names.length) return;
    let cancelled = false;
    api
      .plot(job.id, plot.name, names, "real", 2000)
      .then((data) => {
        if (cancelled) return;
        const out: Record<string, number> = {};
        for (const [ref, vec] of Object.entries(supplies)) {
          const v = data.traces[vec]?.values;
          if (v?.length) out[ref] = v[v.length - 1]!;
        }
        setSupplyCurrents(out);
      })
      .catch(() => setSupplyCurrents({}));
    return () => {
      cancelled = true;
    };
  }, [job, netlist]);
  // parts that would burn: ratings exceeded in the last simulation
  useEffect(() => {
    setDamage([]);
    setDamageClosed(false);
    const limits = netlist?.limits ?? [];
    if (!job || job.state !== "done" || !limits.length) return;
    let cancelled = false;
    schematicApi
      .damage(job.id, limits)
      .then((d) => {
        if (!cancelled) setDamage(d);
      })
      .catch(() => setDamage([]));
    return () => {
      cancelled = true;
    };
  }, [job, netlist]);
  const damaged = useMemo(
    () =>
      damageByRef(
        damage,
        glows,
        (ref) => {
          const ind = netlist?.indicators?.[ref];
          const g = glows[ref];
          return ind && g ? `${ref}: ${glowText(ind, g)}.` : null;
        },
        sch.components.map((c) => c.ref),
      ),
    [damage, glows, netlist, sch.components],
  );
  const burnt = useMemo(
    () => Object.fromEntries(damaged.map((d) => [d.ref, d.causes.join(" ")])),
    [damaged],
  );
  useEffect(() => {
    if (onDocumentChange) {
      onDocumentChange(sch);
      return;
    }
    try {
      localStorage.setItem(STORAGE, JSON.stringify(sch));
    } catch {
      /* storage unavailable */
    }
  }, [sch, onDocumentChange]);

  const symbols = useMemo(
    () =>
      Object.fromEntries((library?.symbols ?? []).map((s) => [s.kind, s])) as Record<
        string,
        SymbolDef
      >,
    [library],
  );

  const change = useCallback((next: Schematic) => {
    setSch((prev) => {
      setPast((p) => [...p.slice(-99), prev]);
      setFuture([]);
      return next;
    });
  }, []);
  const replace = (next: Schematic) => {
    change(pruneOrphanSupplyLabels(next));
    setSelection(null);
    setJob(null);
    setNetlist(null);
    setActiveStep("circuit");
  };
  const undo = useCallback(() => {
    setPast((p) => {
      if (!p.length) return p;
      setSch((cur) => {
        setFuture((f) => [cur, ...f]);
        return p[p.length - 1]!;
      });
      return p.slice(0, -1);
    });
  }, []);
  const redo = useCallback(() => {
    setFuture((f) => {
      if (!f.length) return f;
      setSch((cur) => {
        setPast((p) => [...p, cur]);
        return f[0]!;
      });
      return f.slice(1);
    });
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      if (
        (e.target as HTMLElement).tagName === "INPUT" ||
        (e.target as HTMLElement).tagName === "TEXTAREA"
      )
        return;
      if (e.key === "z") {
        e.preventDefault();
        undo();
      } else if (e.key === "y") {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  const probeColors = useMemo(
    () =>
      Object.fromEntries(
        sch.probes.map((p, i) => [p.id, TRACE_COLORS[i % TRACE_COLORS.length] ?? "#888"]),
      ),
    [sch.probes],
  );

  const addBenchSupply = () => {
    const existing = new Set(sch.components.map((c) => c.params.bench_id));
    let number = 1;
    while (existing.has(`PS${number}`)) number++;
    const id = `PS${number}`;
    const baseY = Math.max(0, ...sch.components.map((c) => c.y)) + 10;
    const components = [...sch.components];
    const labels = [...sch.labels];
    const probes = [...sch.probes];
    for (let ch = 1; ch <= 3; ch++) {
      const ref = nextRef({ ...sch, components }, "V");
      const x = (ch - 1) * 12,
        y = baseY;
      components.push({
        id: `${id}-${ch}`,
        kind: "vdc",
        ref,
        x,
        y,
        rot: 0,
        mirror: false,
        part_id: null,
        params: { dc: ch === 3 ? "5" : "0", ac: "0", bench_id: id, bench_channel: String(ch) },
      });
      labels.push(
        { id: `${id}-p${ch}`, name: `${id}_ch${ch}`, x, y: y - 2 },
        { id: `${id}-n${ch}`, name: "0", x, y: y + 2 },
      );
      probes.push(
        { id: `${id}-i${ch}`, kind: "i", component: ref, pin: "p" },
        { id: `${id}-v${ch}`, kind: "v", target: { net: `${id}_ch${ch}` } },
      );
    }
    const assembly = sch.breadboard ?? emptyBreadboard();
    change({
      ...sch,
      components,
      labels,
      probes,
      breadboard: {
        ...assembly,
        parts: [
          ...assembly.parts,
          ...components
            .filter((c) => c.params.bench_id === id)
            .map((c) => ({ ref: c.ref, package: "fonte-cc", legs: {} })),
        ],
      },
    });
  };
  const running = job?.state === "queued" || job?.state === "running";
  // only the last simulation updates the page (a click on a button may start a new one before
  // the previous finished)
  const stopWatch = useRef<(() => void) | null>(null);
  const simulate = async (target: Schematic = sch, opts: { stay?: boolean } = {}) => {
    stopWatch.current?.();
    stopWatch.current = null;
    if (job && (job.state === "queued" || job.state === "running")) void api.cancel(job.id);
    setError(null);
    setJob(null);
    try {
      const hasScopeWiring = Object.keys(target.bench_scope_connections ?? {}).length > 0;
      const scopeResolved = hasScopeWiring ? await breadboardApi.resolve(target) : resolved;
      const scopeSpec = hasScopeWiring ? (bbSpec ?? (await breadboardApi.spec())) : bbSpec;
      const circuit =
        scopeSpec && scopeResolved
          ? syncScopeProbes(target, scopeSpec.board, scopeResolved)
          : target;
      if (circuit !== target) change(circuit);
      if (view === "protoboard") {
        const assembly = await breadboardApi.check(circuit);
        if (!assembly.ok)
          throw new Error(
            "A montagem difere do esquemático. Corrija as ligações indicadas na conferência antes de simular pela protoboard.",
          );
      }
      const nl = await schematicApi.netlist(circuit);
      setSimulatedCircuit(JSON.stringify({ ...circuit, bench_scope_channels: 0 }));
      setNetlist(nl);
      setResultProbes(nl.probes.filter((p) => p.probe_id !== null).map((p) => p.name));
      const r = await schematicApi.simulate(circuit);
      setWarnings(r.warnings);
      setJob({ id: r.job_id, state: "queued", progress: 0, message: "na fila" });
      if (!opts.stay) activateStep("results");
      stopWatch.current = watchJob(r.job_id, (j) => setJob(j));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  // a push-button clicked in the drawing: keep the new position and simulate again at once, so
  // LEDs, lamps and motors follow it
  const operate = (next: Schematic, comp: Component) => {
    change(next);
    if (liveActive) return;
    const sym = symbols[comp.kind];
    const text = `${comp.ref}: ${switchText(comp, stateDefault(sym))}`;
    if (!next.analyses.length) {
      setNotice(`${text}. Escolha uma análise e clique em Simular para ver o efeito.`);
      return;
    }
    setNotice(`${text}. Simulando de novo…`);
    void simulate(next, { stay: true });
  };
  const showNetlist = async () => {
    try {
      setNetlist(await schematicApi.netlist(sch));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
    setPanel("netlist");
  };

  const save = () =>
    download(
      new Blob([JSON.stringify(sch, null, 2)], { type: "application/json" }),
      `${slug(sch.title)}.circ.json`,
    );
  const open = async (file: File) => {
    try {
      const doc = JSON.parse(await file.text()) as Schematic;
      if (!Array.isArray(doc.components)) throw new Error("Arquivo sem componentes");
      replace(upgradeSchematic({ ...emptySchematic(), ...doc }));
    } catch (e) {
      setError(`Arquivo inválido: ${(e as Error).message}`);
    }
  };
  const doImport = async (text: string) => {
    try {
      const r = await schematicApi.importNetlist(text);
      replace(r.schematic);
      setWarnings(r.warnings);
      setImportText(null);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const exportNetlist = async () => {
    try {
      const nl = await schematicApi.netlist(sch);
      download(new Blob([nl.netlist], { type: "text/plain" }), `${slug(sch.title)}.cir`);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const exportKicad = async () => {
    try {
      download(await schematicApi.kicad(sch), `${slug(sch.title)}.net`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!library)
    return (
      <main className="single">
        {error ? <p className="error">{error}</p> : <p>Carregando…</p>}
      </main>
    );

  // a group whose symbols are all hidden (Outros: only the subcircuit) is not listed
  const groups = [
    ...new Set(library.symbols.filter((s) => !HIDDEN_KINDS.has(s.kind)).map((s) => s.group)),
  ];
  const selectedComp =
    selection?.kind === "component" ? sch.components.find((c) => c.id === selection.id) : undefined;
  const selectedLabel =
    selection?.kind === "label" ? sch.labels.find((l) => l.id === selection.id) : undefined;

  return (
    <main
      className={`schematic-page workspace-mode-${activeStep} workspace-view-${view}${liveActive ? " workspace-live" : ""}`}
    >
      <WorkspaceSteps
        active={activeStep}
        resultsAvailable={job !== null}
        onSelect={(step) => {
          if (liveActive && step !== "circuit") {
            setNotice(
              "Pare a bancada antes de configurar outra análise ou abrir resultados anteriores.",
            );
            return;
          }
          activateStep(step);
        }}
      />
      {view === "protoboard" && !liveActive && (
        <BenchSupply
          liveData={liveData}
          spec={bbSpec}
          schematic={sch}
          onChange={change}
          job={
            simulatedCircuit === JSON.stringify({ ...sch, bench_scope_channels: 0 }) ? job : null
          }
        />
      )}
      {view === "protoboard" && !liveActive && (
        <BenchScope
          schematic={sch}
          onChange={change}
          job={
            simulatedCircuit === JSON.stringify({ ...sch, bench_scope_channels: 0 }) ? job : null
          }
          probeNames={resultProbes}
        />
      )}
      <div className="simulator-workbench">
        {view === "protoboard" && (
          <InteractiveBench
            meter={liveMeter}
            onMeterChange={setLiveMeter}
            onChange={change}
            schematic={sch}
            spec={bbSpec}
            resolved={resolved}
            onActiveChange={(active) => {
              setLiveActive(active);
              if (active) activateStep("circuit");
            }}
            onSnapshot={setLiveData}
            instruments={
              <BenchSupply
                liveData={liveData}
                spec={bbSpec}
                schematic={sch}
                onChange={change}
                job={null}
              />
            }
          />
        )}
        <div
          ref={circuitRef}
          className="circuit-workspace"
          tabIndex={-1}
          role="region"
          aria-label="Circuito"
        >
          <div className="toolbar row wrap">
            <div className="segmented" role="group" aria-label="Vista">
              <button
                className={view === "esquematico" ? "tab active" : "tab"}
                onClick={() => setView("esquematico")}
              >
                Esquemático 2D
              </button>
              <button
                className={view === "protoboard" ? "tab active" : "tab"}
                onClick={() => setView("protoboard")}
              >
                Protoboard
              </button>
            </div>
            <input
              className="title-input"
              aria-label="Título do circuito"
              value={sch.title}
              onChange={(e) => change({ ...sch, title: e.target.value })}
            />
            <select
              aria-label="Exemplos"
              value=""
              onChange={(e) => {
                const ex = SCHEMATIC_EXAMPLES[e.target.value];
                if (ex) replace(ex());
                const co = cosimExamples.find((c) => `mcu:${c.name}` === e.target.value);
                if (co) replace(structuredClone(co.schematic));
              }}
            >
              <option value="">Exemplos…</option>
              <optgroup label="Circuitos">
                {Object.keys(SCHEMATIC_EXAMPLES).map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </optgroup>
              {cosimExamples.length > 0 && (
                <optgroup label="Microcontroladores e CLP">
                  {cosimExamples.map((c) => (
                    <option key={c.name} value={`mcu:${c.name}`} title={c.description}>
                      {c.name}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
            <button className="secondary" onClick={() => replace(emptySchematic())}>
              Novo
            </button>
            <button className="secondary" onClick={() => fileRef.current?.click()}>
              Abrir
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".json,.circ.json"
              hidden
              onChange={(e) => e.target.files?.[0] && void open(e.target.files[0])}
            />
            <button className="secondary" onClick={save}>
              Salvar
            </button>
            <button className="secondary" onClick={() => setImportText("")}>
              Importar netlist
            </button>
            <button className="secondary" onClick={() => void exportNetlist()}>
              Exportar netlist
            </button>
            <button
              className="secondary"
              onClick={() => void exportKicad()}
              title="Netlist para o KiCad (Pcbnew: Arquivo → Importar → Netlist)"
            >
              KiCad
            </button>
            <button className="secondary" onClick={undo} disabled={!past.length} title="Ctrl+Z">
              Desfazer
            </button>
            <button className="secondary" onClick={redo} disabled={!future.length} title="Ctrl+Y">
              Refazer
            </button>
            <label className="node-visibility">
              <input
                type="checkbox"
                checked={showNodeNames}
                onChange={(e) => setShowNodeNames(e.target.checked)}
              />
              Exibir nomes dos nós
            </label>
            <label className="bench-actions">
              Adicionar instrumento
              <select
                aria-label="Adicionar instrumento"
                value=""
                onChange={(e) => {
                  const instrument = e.target.value;
                  if (instrument === "supply") addBenchSupply();
                  else if (instrument === "multimeter") {
                    setLiveMeter(true);
                    setView("protoboard");
                  } else if (instrument === "generator") {
                    const ref = nextRef(sch, "G");
                    const assembly = sch.breadboard ?? emptyBreadboard();
                    change({
                      ...sch,
                      components: [
                        ...sch.components,
                        {
                          id: `generator${Date.now()}`,
                          ref,
                          kind: "vsin",
                          x: 0,
                          y: Math.max(0, ...sch.components.map((c) => c.y)) + 10,
                          rot: 0,
                          mirror: false,
                          part_id: null,
                          params: {
                            offset: "0",
                            amplitude: "1",
                            freq: "1k",
                            ac: "1",
                            bench_instrument: "generator",
                          },
                        },
                      ],
                      breadboard: {
                        ...assembly,
                        parts: [...assembly.parts, { ref, package: "gerador", legs: {} }],
                      },
                    });
                  } else if (instrument === "scope2" || instrument === "scope4")
                    change({
                      ...sch,
                      bench_scope_channels: instrument === "scope2" ? 2 : 4,
                      bench_scope_connections: Object.keys(sch.bench_scope_connections ?? {}).length
                        ? sch.bench_scope_connections
                        : {
                            "1": { positive: null, negative: null },
                            "2": { positive: null, negative: null },
                          },
                    });
                }}
              >
                <option value="">Escolher instrumento…</option>
                <option value="supply">Fonte de bancada (3 canais)</option>
                <option value="generator">Gerador de sinais</option>
                <option value="scope2">Osciloscópio de 2 canais</option>
                <option value="scope4">Osciloscópio de 4 canais</option>
                <option value="multimeter">Multímetro</option>
              </select>
            </label>
            <span className="grow" />
            <button onClick={() => void simulate()} disabled={running || liveActive}>
              {running ? "Simulando…" : "Simular"}
            </button>
            {running && job && (
              <button className="secondary" onClick={() => void api.cancel(job.id)}>
                Cancelar
              </button>
            )}
          </div>

          {nodeError && (
            <p className="small muted" role="status">
              {nodeError}
            </p>
          )}
          {importText !== null && (
            <div className="panel import-box">
              <h3>Importar netlist SPICE</h3>
              <p className="small muted">
                A primeira linha é o título (regra do SPICE). Modelos .model/.subckt e linhas sem
                símbolo ficam nas diretivas.
              </p>
              <textarea
                rows={12}
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
              />
              <div className="row">
                <button onClick={() => void doImport(importText)}>Importar</button>
                <label className="button secondary">
                  Arquivo…
                  <input
                    type="file"
                    accept=".cir,.net,.sp,.spice,.txt"
                    hidden
                    onChange={async (e) =>
                      e.target.files?.[0] && setImportText(await e.target.files[0].text())
                    }
                  />
                </label>
                <button className="secondary" onClick={() => setImportText(null)}>
                  Fechar
                </button>
              </div>
            </div>
          )}

          {view === "esquematico" && (
            <div className="schematic-toolstrip" role="group" aria-label="Ferramentas de desenho">
              <button
                type="button"
                className="secondary library-toggle"
                aria-expanded={libraryOpen}
                aria-controls="symbol-library"
                onClick={() => setLibraryOpen(!libraryOpen)}
              >
                {libraryOpen ? "Recolher biblioteca" : "Adicionar componente"}
              </button>
              <div className="drawing-tools">
                {EDIT_TOOLS.map(([t, label]) => (
                  <button
                    key={label}
                    className={JSON.stringify(t) === JSON.stringify(tool) ? "tool active" : "tool"}
                    aria-pressed={JSON.stringify(t) === JSON.stringify(tool)}
                    onClick={() => setTool(t)}
                  >
                    {label}
                  </button>
                ))}
                <button
                  className="tool"
                  title="Liga com fio reto os pinos livres que estão alinhados (mesma linha ou coluna) e sem nada no caminho"
                  onClick={() => {
                    const wires = autoWire(sch, symbols);
                    if (wires.length) change({ ...sch, wires: [...sch.wires, ...wires] });
                    setNotice(
                      wires.length
                        ? `${wires.length} fio(s) lançado(s) entre pinos alinhados (Ctrl+Z desfaz)`
                        : "Nenhum par de pinos livres alinhado com caminho livre",
                    );
                  }}
                >
                  Ligar pinos alinhados
                </button>
                <button
                  className="tool"
                  title="Apaga todos os componentes, fios, rótulos e ponteiras do esquemático (Ctrl+Z desfaz)"
                  disabled={!sch.components.length && !sch.wires.length && !sch.labels.length}
                  onClick={() => {
                    if (
                      !window.confirm(
                        "Limpar o circuito? Todos os componentes e fios serão apagados.",
                      )
                    )
                      return;
                    change({
                      ...sch,
                      components: [],
                      wires: [],
                      labels: [],
                      probes: [],
                      breadboard: null,
                      bench_scope_connections: {},
                    });
                    setNotice("Circuito limpo (Ctrl+Z desfaz)");
                  }}
                >
                  Limpar circuito
                </button>
                <button
                  className="tool"
                  title="Ocupa a tela inteira com o circuito (Esc volta)"
                  onClick={() => {
                    const el = circuitRef.current;
                    if (!el) return;
                    if (document.fullscreenElement) void document.exitFullscreen();
                    else void el.requestFullscreen?.();
                  }}
                >
                  Tela cheia
                </button>
              </div>
            </div>
          )}
          {notice && (
            <p className="small notice" role="status">
              {notice}
            </p>
          )}
          {!damageClosed && (
            <DamageAlert
              parts={damaged}
              onClose={() => setDamageClosed(true)}
              onSelect={(ref) => {
                const c = sch.components.find((x) => x.ref === ref);
                if (c) setSelection({ kind: "component", id: c.id });
              }}
            />
          )}

          {view === "protoboard" && bbSpec ? (
            <BreadboardView
              schematic={sch}
              onChange={change}
              spec={bbSpec}
              resolved={resolved}
              motion={motion}
              burnt={burnt}
              glows={glows}
              supplyCurrents={liveData ? liveSupplyCurrents : supplyCurrents}
              onOperate={operate}
              library={symbols}
            />
          ) : (
            <div className={`schematic-layout${libraryOpen ? " library-open" : ""}`}>
              <aside
                id="symbol-library"
                className="panel palette"
                aria-label="Biblioteca de símbolos"
                hidden={!libraryOpen}
              >
                <h3>Biblioteca de componentes</h3>
                <p className="small muted">Escolha um símbolo e posicione-o no circuito.</p>
                {groups.map((g) => (
                  <details key={g} open>
                    <summary>{g}</summary>
                    {library.symbols
                      .filter(
                        (s) =>
                          s.group === g &&
                          !HIDDEN_KINDS.has(s.kind) &&
                          (!/^[vi](dc|sin|pulse|pwl)$/.test(s.kind) || /[vi]dc/.test(s.kind)),
                      )
                      .map((s) => (
                        <button
                          key={s.kind}
                          className={
                            tool.kind === "place" && tool.symbol === s.kind
                              ? "palette-item active"
                              : "palette-item"
                          }
                          title={s.description || s.label}
                          onClick={() => setTool({ kind: "place", symbol: s.kind })}
                        >
                          {s.kind === "vdc"
                            ? "Fonte de tensão (CC/CA)"
                            : s.kind === "idc"
                              ? "Fonte de corrente (CC/CA)"
                              : s.kind === "led"
                                ? "LED genérico"
                                : s.kind === "lamp"
                                  ? "Lâmpada genérica"
                                  : s.label}
                        </button>
                      ))}
                    {g === "LEDs e lâmpadas" && (
                      <IndicatorPalette
                        parts={indicatorParts}
                        tool={tool}
                        onPick={(t) => setTool(t)}
                      />
                    )}
                  </details>
                ))}
              </aside>

              <SchematicEditor
                nodeNames={showNodeNames ? nodeMap : {}}
                schematic={sch}
                library={symbols}
                tool={tool}
                setTool={setTool}
                selection={selection}
                setSelection={setSelection}
                onChange={change}
                probeColors={probeColors}
                motion={motion}
                glows={glows}
                burnt={burnt}
                onNotice={setNotice}
                onOperate={operate}
              />

              <aside className="panel properties" aria-label="Propriedades">
                <h3>Propriedades</h3>
                <label className="component-picker">
                  Componente selecionado
                  <select
                    aria-label="Selecionar componente"
                    value={selectedComp?.id ?? ""}
                    onChange={(event) => {
                      setSelection(
                        event.target.value ? { kind: "component", id: event.target.value } : null,
                      );
                      setTool({ kind: "select" });
                    }}
                  >
                    <option value="">Selecione no circuito…</option>
                    {sch.components.map((component) => (
                      <option key={component.id} value={component.id}>
                        {component.ref} · {symbols[component.kind]?.label ?? component.kind}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedComp ? (
                  <ComponentProps
                    comp={selectedComp}
                    sym={symbols[selectedComp.kind]}
                    onChange={(c) =>
                      change({
                        ...sch,
                        components: sch.components.map((x) => (x.id === c.id ? c : x)),
                      })
                    }
                    onDelete={() => {
                      change(removeSources(sch, [selectedComp.id]));
                      setSelection(null);
                    }}
                    refsInUse={sch.components
                      .filter((x) => x.id !== selectedComp.id)
                      .map((x) => x.ref.toLowerCase())}
                  />
                ) : null}
                {selectedComp &&
                  glows[selectedComp.ref] &&
                  netlist?.indicators?.[selectedComp.ref] && (
                    <p className="small" role="status">
                      {glowText(netlist.indicators[selectedComp.ref]!, glows[selectedComp.ref]!)}
                    </p>
                  )}
                {selectedComp && MANUAL_SWITCH_KINDS.has(selectedComp.kind) && (
                  <p className="small switch-status" role="status">
                    <button
                      type="button"
                      className="secondary small-btn"
                      onClick={() => {
                        const t = toggleSwitch(
                          selectedComp,
                          stateDefault(symbols[selectedComp.kind]),
                        );
                        operate(
                          {
                            ...sch,
                            components: sch.components.map((x) => (x.id === t.id ? t : x)),
                          },
                          t,
                        );
                      }}
                    >
                      {switchPosition(selectedComp, stateDefault(symbols[selectedComp.kind])) ===
                      "pressed"
                        ? "Soltar"
                        : "Apertar"}
                    </button>{" "}
                    {switchText(selectedComp, stateDefault(symbols[selectedComp.kind]))}
                  </p>
                )}
                {selectedComp && burnt[selectedComp.ref] && (
                  <p className="small error" role="status">
                    {burnt[selectedComp.ref]}
                  </p>
                )}
                {selection?.kind === "group" && (
                  <div>
                    <h3>Seleção múltipla</h3>
                    <p className="small muted">
                      {selection.components.length} componente(s), {selection.wires.length} fio(s) e{" "}
                      {selection.labels.length} rótulo(s). Arraste um deles para mover tudo; Ctrl+C
                      copia, Ctrl+V cola no cursor, Ctrl+D duplica.
                    </p>
                    <button
                      className="secondary"
                      onClick={() => {
                        const doc = removeSources(sch, selection.components);
                        change({
                          ...doc,
                          wires: doc.wires.filter((w) => !selection.wires.includes(w.id)),
                          labels: doc.labels.filter((l) => !selection.labels.includes(l.id)),
                        });
                        setSelection(null);
                      }}
                    >
                      Apagar seleção
                    </button>
                  </div>
                )}
                {selectedComp && bbSpec && resolved && (
                  <SelectedPackage
                    view={resolved.parts.find((p) => p.ref === selectedComp.ref)}
                    packages={bbSpec.packages}
                  />
                )}
                {selectedComp ? null : selectedLabel ? (
                  <div>
                    <h3>Rótulo de nó</h3>
                    <label>
                      Nome do nó
                      <input
                        value={selectedLabel.name}
                        onChange={(e) =>
                          change({
                            ...sch,
                            labels: sch.labels.map((l) =>
                              l.id === selectedLabel.id
                                ? {
                                    ...l,
                                    name: e.target.value.replace(/[^A-Za-z0-9_+-]/g, "") || "n",
                                  }
                                : l,
                            ),
                          })
                        }
                      />
                    </label>
                    <p className="small muted">
                      Rótulos de mesmo nome são o mesmo nó; “0” ou “gnd” é a terra.
                    </p>
                  </div>
                ) : selection?.kind === "wire" ? (
                  <div>
                    <h3>Fio</h3>
                    <button
                      className="secondary"
                      onClick={() => {
                        change({ ...sch, wires: sch.wires.filter((w) => w.id !== selection.id) });
                        setSelection(null);
                      }}
                    >
                      Apagar fio
                    </button>
                  </div>
                ) : selection?.kind === "group" ? null : (
                  <p className="small muted">
                    Selecione um componente no desenho ou na lista acima para editar seus valores.
                    Para inserir uma peça, use “Adicionar componente”.
                  </p>
                )}
                <h3>Ponteiras</h3>
                {sch.probes.length === 0 && (
                  <p className="small muted">Nenhuma. Use as ferramentas “Ponteira”.</p>
                )}
                <ul className="probe-list">
                  {sch.probes.map((p) => (
                    <li key={p.id}>
                      <span className="swatch" style={{ background: probeColors[p.id] }} />
                      <input
                        aria-label="Nome da ponteira"
                        readOnly={/^bench-scope-ch[1-4]$/.test(p.id)}
                        placeholder={probeDefault(p)}
                        value={p.name ?? ""}
                        onChange={(e) =>
                          change({
                            ...sch,
                            probes: sch.probes.map((x) =>
                              x.id === p.id ? { ...x, name: e.target.value || null } : x,
                            ),
                          })
                        }
                      />
                      <button
                        className="secondary small-btn"
                        aria-label="Remover ponteira"
                        onClick={() => {
                          const channel = /^bench-scope-ch([1-4])$/.exec(p.id);
                          change(
                            channel
                              ? disconnectScope(sch, Number(channel[1]))
                              : { ...sch, probes: sch.probes.filter((x) => x.id !== p.id) },
                          );
                        }}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              </aside>
            </div>
          )}
        </div>

        <section
          ref={analysisRef}
          className="panel analysis-panel workspace-section"
          hidden={activeStep !== "analysis"}
          tabIndex={-1}
          aria-label="Configurar análise"
        >
          <div className="section-heading">
            <div>
              <h3>Configurar análise</h3>
              <p className="small muted">
                Escolha as análises e ajuste as condições antes de simular.
              </p>
            </div>
          </div>
          <div className="tabs" role="tablist">
            {(
              [
                ["analyses", "Análises"],
                ["sweep", "Varredura, Monte Carlo e pior caso"],
                ["params", "Temperatura, parâmetros e diretivas"],
                ["netlist", "Netlist"],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                className={panel === k ? "tab active" : "tab"}
                onClick={() => (k === "netlist" ? void showNetlist() : setPanel(k))}
              >
                {label}
              </button>
            ))}
          </div>
          {panel === "analyses" && <AnalysesPanel sch={sch} library={library} onChange={change} />}
          {panel === "sweep" && <SweepPanel sch={sch} onChange={change} />}
          {panel === "params" && <ParamsPanel sch={sch} onChange={change} />}
          {panel === "netlist" && netlist && (
            <div>
              <pre className="netlist-view">{netlist.netlist}</pre>
              {netlist.spreads.length > 0 && (
                <table className="params">
                  <thead>
                    <tr>
                      <th>Tolerância</th>
                      <th>Mín.</th>
                      <th>Nominal</th>
                      <th>Máx.</th>
                      <th>Fonte</th>
                    </tr>
                  </thead>
                  <tbody>
                    {netlist.spreads.map((s) => (
                      <tr key={s.component}>
                        <td>
                          {s.component}.{s.param}
                        </td>
                        <td className="num">{s.low.toPrecision(4)}</td>
                        <td className="num">{s.nominal.toPrecision(4)}</td>
                        <td className="num">{s.high.toPrecision(4)}</td>
                        <td className="small">{s.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </section>

        <section
          ref={resultsRef}
          className="simulation-output workspace-section"
          hidden={activeStep !== "results"}
          tabIndex={-1}
          aria-label="Resultados da simulação"
        >
          <div className="section-heading">
            <div>
              <h3>Resultados</h3>
              <p className="small muted">Sinais, medições e avisos da execução.</p>
            </div>
          </div>
          {job ? (
            <section className="panel">
              <div className="row">
                <b>{STATE_LABEL[job.state]}</b>
                {running && <progress value={job.progress} max={1} />}
                <span className="small muted">
                  {job.message}
                  {job.elapsed_s ? ` · ${job.elapsed_s.toFixed(2).replace(".", ",")} s` : ""}
                  {job.backend ? ` · ${job.backend}` : ""}
                </span>
              </div>
              {job.error && (
                <div className="error">
                  <p>{job.error.message}</p>
                  {job.error.suggestions.length > 0 && (
                    <ul>
                      {job.error.suggestions.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  )}
                  {job.error.log && <pre>{job.error.log.slice(-3000)}</pre>}
                </div>
              )}
              {job.state === "done" && (
                <ResultsView job={job} probeNames={resultProbes} onJobUpdate={setJob} />
              )}
            </section>
          ) : (
            <div className="panel results-empty">
              <h3>Pronto para a primeira simulação</h3>
              <p className="muted">
                Confira o circuito e as análises. Ao clicar em Simular, os resultados aparecerão
                aqui.
              </p>
              <button className="secondary" onClick={() => activateStep("analysis")}>
                Revisar análises
              </button>
            </div>
          )}
        </section>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {(warnings.length > 0 ||
        (netlist?.warnings.length ?? 0) > 0 ||
        (job?.warnings?.length ?? 0) > 0) && (
        <ul className="warnings">
          {[...new Set([...warnings, ...(netlist?.warnings ?? []), ...(job?.warnings ?? [])])].map(
            (w) => (
              <li key={w}>{w}</li>
            ),
          )}
        </ul>
      )}
    </main>
  );
}

function slug(s: string): string {
  return (
    s
      .normalize("NFD")
      .replace(/[^\w]+/g, "-")
      .replace(/^-|-$/g, "")
      .toLowerCase() || "circuito"
  );
}

function probeDefault(p: Schematic["probes"][number]): string {
  if (p.kind === "i") return `i(${p.component?.toLowerCase()})`;
  if (p.kind === "p") return `p(${p.component?.toLowerCase()})`;
  if (p.target?.net)
    return p.kind === "vdiff" ? `v(${p.target.net},${p.reference?.net})` : `v(${p.target.net})`;
  return p.kind === "vdiff" ? "v(+,−)" : "v(nó)";
}

function ParamInput({
  def,
  value,
  onChange,
}: {
  def: ParamDef;
  value: string | undefined;
  onChange: (v: string) => void;
}) {
  const unit = def.unit ? ` (${def.unit})` : "";
  if (def.type === "code") return <CodeParam def={def} value={value} onChange={onChange} />;
  if (def.type === "choice")
    return (
      <label title={def.help}>
        {def.label}
        <select value={value ?? def.default} onChange={(e) => onChange(e.target.value)}>
          {def.choices.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
    );
  return (
    <label title={def.help}>
      {def.label}
      {unit}
      <input
        value={value ?? ""}
        placeholder={def.default || (def.optional ? "opcional" : "")}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function CodeParam({
  def,
  value,
  onChange,
}: {
  def: ParamDef;
  value: string | undefined;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const text = value ?? def.default;
  const first = text.split("\n").find((l) => l.trim()) ?? "";
  return (
    <div className="code-param">
      <span>{def.label}</span>
      <button className="secondary small" onClick={() => setOpen(true)}>
        Editar
      </button>
      <code className="small muted">{first.slice(0, 40)}</code>
      {open && (
        <ProgramEditor
          title={def.label}
          kind={def.name}
          value={text}
          onSave={onChange}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}

function ComponentProps({
  comp,
  sym,
  onChange,
  onDelete,
  refsInUse,
}: {
  comp: Component;
  sym: SymbolDef | undefined;
  onChange: (c: Component) => void;
  onDelete: () => void;
  refsInUse: string[];
}) {
  const [parts, setParts] = useState<PartOut[]>([]);
  const [refDraft, setRefDraft] = useState(comp.ref);
  useEffect(() => setRefDraft(comp.ref), [comp.id, comp.ref]);
  useEffect(() => {
    if (!sym?.catalogue.length) {
      setParts([]);
      return;
    }
    schematicApi
      .parts(comp.kind)
      .then(setParts)
      .catch(() => setParts([]));
  }, [comp.kind, sym]);
  if (!sym) return <p className="error">Símbolo desconhecido: {comp.kind}</p>;
  const part = parts.find((p) => p.id === comp.part_id);
  const generic = !comp.part_id;
  const keepForPart = new Set(["ic_op", "vcc", "vee", "v0", "vt0", "il", "diode"]);
  const commitRef = () => {
    const r = refDraft.replace(/[^A-Za-z0-9_]/g, "");
    if (r && !refsInUse.includes(r.toLowerCase())) onChange({ ...comp, ref: r });
    else setRefDraft(comp.ref);
  };
  return (
    <div>
      <h3>{sym.label}</h3>
      {sym.description && <p className="small muted">{sym.description}</p>}
      {comp.kind !== "ground" && (
        <label>
          Designador
          <input
            value={refDraft}
            onChange={(e) => setRefDraft(e.target.value)}
            onBlur={commitRef}
            onKeyDown={(e) => e.key === "Enter" && commitRef()}
          />
        </label>
      )}
      <div className="row">
        <button
          className="secondary small-btn"
          onClick={() => onChange({ ...comp, rot: ((comp.rot + 90) % 360) as Component["rot"] })}
        >
          Girar (R)
        </button>
        <button
          className="secondary small-btn"
          onClick={() => onChange({ ...comp, mirror: !comp.mirror })}
        >
          Espelhar (M)
        </button>
        <button className="secondary small-btn" onClick={onDelete}>
          Apagar
        </button>
      </div>
      {sym.catalogue.length > 0 && (
        <label>
          Peça
          <select
            value={comp.part_id ?? ""}
            onChange={(e) => {
              const p = parts.find((x) => x.id === e.target.value);
              const params = { ...comp.params };
              if (p) params.part_label = p.part_number;
              else delete params.part_label;
              onChange({ ...comp, part_id: p ? p.id : null, params });
            }}
          >
            <option value="">modelo genérico (didático)</option>
            {parts.map((p) => (
              <option key={p.id} value={p.id}>
                {p.part_number} · {p.manufacturer}
                {p.released ? "" : ` (${p.status}, não revisado)`}
              </option>
            ))}
          </select>
        </label>
      )}
      {part && !part.released && (
        <p className="small status-atencao">
          Peça não revisada: o modelo usa os valores extraídos do datasheet, ainda sem a sua
          conferência.
        </p>
      )}
      {/^[vi](dc|sin|pulse)$/.test(comp.kind) && (
        <SourceControls component={comp} onChange={onChange} />
      )}
      {sym.params.some((p) => p.name === "program") && (
        <FirmwareControls component={comp} onChange={onChange} />
      )}
      {comp.firmware && (
        <p className="small muted">
          O código-fonte anterior fica guardado. Retire o firmware para voltar a editá-lo.
        </p>
      )}
      {sym.params
        .filter(
          (d) =>
            (!comp.firmware || !["program", "instr_us", "pwm"].includes(d.name)) &&
            (generic || keepForPart.has(d.name)) &&
            (!/^[vi](dc|sin|pulse)$/.test(comp.kind) ||
              ["ac", "tol", "phase", "delay"].includes(d.name)),
        )
        .map((d) => (
          <ParamInput
            key={d.name}
            def={d}
            value={comp.params[d.name]}
            onChange={(v) => {
              const params = { ...comp.params };
              if (v === "") delete params[d.name];
              else params[d.name] = v;
              onChange({ ...comp, params });
            }}
          />
        ))}
      {!generic && (
        <p className="small muted">
          Modelo e faixa (Monte Carlo/pior caso) vêm do datasheet da peça.
        </p>
      )}
    </div>
  );
}

function AnalysesPanel({
  sch,
  library,
  onChange,
}: {
  sch: Schematic;
  library: Library;
  onChange: (s: Schematic) => void;
}) {
  const kinds = Object.keys(library.analyses) as AnalysisKind[];
  const update = (i: number, a: Analysis) =>
    onChange({ ...sch, analyses: sch.analyses.map((x, k) => (k === i ? a : x)) });
  return (
    <div>
      {sch.analyses.map((a, i) => (
        <fieldset key={i} className="analysis">
          <legend>
            <label className="inline">
              <input
                type="checkbox"
                checked={a.enabled}
                onChange={(e) => update(i, { ...a, enabled: e.target.checked })}
              />{" "}
              {library.analyses[a.kind]?.label ?? a.kind}
            </label>{" "}
            <button
              className="secondary small-btn"
              onClick={() => onChange({ ...sch, analyses: sch.analyses.filter((_, k) => k !== i) })}
            >
              Remover
            </button>
          </legend>
          <div className="param-grid">
            {library.analyses[a.kind]?.params.map((d) => (
              <ParamInput
                key={d.name}
                def={d}
                value={a.params[d.name]}
                onChange={(v) => update(i, { ...a, params: { ...a.params, [d.name]: v } })}
              />
            ))}
          </div>
          {a.kind === "tran" && (
            <TranSuggestionBox
              sch={sch}
              analysis={a}
              labels={Object.fromEntries(
                (library.analyses.tran?.params ?? []).map((d) => [d.name, d.label]),
              )}
              onApply={(params) => update(i, { ...a, params: { ...a.params, ...params } })}
            />
          )}
        </fieldset>
      ))}
      <div className="row">
        {kinds.map((k) => {
          const def = library.analyses[k];
          if (!def) return null;
          return (
            <button
              key={k}
              className="secondary"
              onClick={() =>
                onChange({
                  ...sch,
                  analyses: [
                    ...sch.analyses,
                    {
                      kind: k,
                      params: Object.fromEntries(
                        def.params.filter((d) => d.default).map((d) => [d.name, d.default]),
                      ),
                      enabled: true,
                    },
                  ],
                })
              }
            >
              + {def.label}
            </button>
          );
        })}
      </div>
      <p className="small muted">
        Fourier/FFT, THD, Bode e medidas são calculados sobre os resultados (aba de resultados).
        Notação SPICE: 4.7k, 10u, 1meg (m = mili, meg = mega).
      </p>
    </div>
  );
}

/** Suggested .tran settings computed from the circuit; "Aplicar" copies them into the fields,
 * which stay editable. */
function TranSuggestionBox({
  sch,
  analysis,
  labels,
  onApply,
}: {
  sch: Schematic;
  analysis: Analysis;
  labels: Record<string, string>;
  onApply: (params: Record<string, string>) => void;
}) {
  const [sug, setSug] = useState<TranSuggestion | null>(null);
  const [failure, setFailure] = useState("");
  // only the circuit matters, not the analysis fields being typed
  const circuitKey = useMemo(
    () =>
      JSON.stringify({
        c: sch.components,
        w: sch.wires,
        l: sch.labels,
      }),
    [sch.components, sch.wires, sch.labels],
  );
  const latest = useRef(sch);
  latest.current = sch;
  useEffect(() => {
    let alive = true;
    const t = window.setTimeout(() => {
      schematicApi
        .tranSuggestion(latest.current)
        .then((r) => {
          if (!alive) return;
          setSug(r);
          setFailure("");
        })
        .catch((e: Error) => {
          if (!alive) return;
          setSug(null);
          setFailure(e.message);
        });
    }, 400);
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [circuitKey]);
  if (failure) return <p className="small muted">Sugestão indisponível: {failure}</p>;
  if (!sug) return <p className="small muted">Calculando a sugestão para este circuito…</p>;
  const names = ["tstop", "tstep", "tstart", "tmax", "uic"];
  // a blank field means its default: start 0, UIC "não"
  const DEFAULTS: Record<string, string> = { tstart: "0", uic: "não" };
  const current = (n: string) => (analysis.params[n] ?? "").trim() || (DEFAULTS[n] ?? "");
  const same = names.every((n) => current(n) === (sug.params[n] ?? ""));
  const show = (n: string, v: string) =>
    n === "uic" || !v ? v : `${v.replace(/u$/, "µ").replace(".", ",")}s`;
  return (
    <div className="tran-suggestion">
      <div className="row">
        <b>Sugestão para este circuito</b>
        <button className="small-btn" disabled={same} onClick={() => onApply(sug.params)}>
          {same ? "Sugestão aplicada" : "Aplicar sugestão"}
        </button>
      </div>
      <table className="params">
        <thead>
          <tr>
            <th>Parâmetro</th>
            <th>Sugerido</th>
            <th>Atual</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {names.map((n) => {
            const proposed = sug.params[n] ?? "";
            const now = current(n);
            return (
              <tr key={n}>
                <td>{labels[n] ?? n}</td>
                <td className="num">{proposed ? show(n, proposed) : "padrão do ngspice"}</td>
                <td className="num">
                  {now ? show(n, now) : n === "tstep" ? "tempo final/1000" : "padrão do ngspice"}
                </td>
                <td>
                  {now !== proposed && (
                    <button
                      className="secondary small-btn"
                      title="Copiar só este valor para o campo"
                      onClick={() => onApply({ [n]: proposed })}
                    >
                      usar
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <ul className="small">
        {sug.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      {sug.warnings.length > 0 && (
        <ul className="warnings small">
          {sug.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <details>
        <summary className="small">Como foi calculado</summary>
        <CalcSteps steps={sug.steps} />
      </details>
      <p className="small muted">
        A sugestão é um ponto de partida: os campos acima continuam editáveis. Com o passo máximo em
        branco, o simulador já usa o valor sugerido quando o padrão do ngspice pularia os sinais
        rápidos.
      </p>
    </div>
  );
}

function SweepPanel({ sch, onChange }: { sch: Schematic; onChange: (s: Schematic) => void }) {
  const sw = sch.sweep ?? emptySweep();
  const set = (patch: Partial<Schematic["sweep"]>) =>
    onChange({ ...sch, sweep: { ...sw, ...patch } });
  const measure = sw.measure ?? {
    analysis: "op" as AnalysisKind,
    vector: "",
    kind: "final" as MeasureKind,
  };
  const setMeasure = (patch: Partial<typeof measure>) => set({ measure: { ...measure, ...patch } });
  return (
    <div className="param-grid">
      <label>
        Tipo
        <select value={sw.kind} onChange={(e) => set({ kind: e.target.value as typeof sw.kind })}>
          <option value="none">execução única</option>
          <option value="step">STEP paramétrico</option>
          <option value="temp">varredura de temperatura</option>
          <option value="montecarlo">Monte Carlo</option>
          <option value="worstcase">pior caso</option>
        </select>
      </label>
      {sw.kind === "step" && (
        <label title="R1.value, V1.dc, C2.value ou param:NOME (um .param)">
          Parâmetro
          <input
            value={sw.target ?? ""}
            placeholder="R1.value ou param:R0"
            onChange={(e) => set({ target: e.target.value })}
          />
        </label>
      )}
      {(sw.kind === "step" || sw.kind === "temp") && (
        <>
          <label>
            Espaçamento
            <select
              value={sw.spacing}
              onChange={(e) => set({ spacing: e.target.value as typeof sw.spacing })}
            >
              <option value="list">lista</option>
              <option value="lin">linear</option>
              <option value="dec">por década</option>
              <option value="oct">por oitava</option>
            </select>
          </label>
          {sw.spacing === "list" ? (
            <label>
              Valores {sw.kind === "temp" ? "(°C)" : ""}
              <input
                value={sw.values.join(" ")}
                placeholder="1k 2.2k 4.7k"
                onChange={(e) => set({ values: e.target.value.split(/[\s;]+/).filter(Boolean) })}
              />
            </label>
          ) : (
            <>
              <label>
                Início
                <input value={sw.start ?? ""} onChange={(e) => set({ start: e.target.value })} />
              </label>
              <label>
                Fim
                <input value={sw.stop ?? ""} onChange={(e) => set({ stop: e.target.value })} />
              </label>
              {sw.spacing === "lin" ? (
                <label>
                  Passo
                  <input value={sw.step ?? ""} onChange={(e) => set({ step: e.target.value })} />
                </label>
              ) : (
                <label>
                  Pontos
                  <input
                    value={sw.points ?? 5}
                    onChange={(e) => set({ points: Number(e.target.value) || 1 })}
                  />
                </label>
              )}
            </>
          )}
        </>
      )}
      {sw.kind === "montecarlo" && (
        <>
          <label>
            Execuções
            <input
              value={sw.runs}
              onChange={(e) =>
                set({ runs: Math.max(1, Math.min(1000, Number(e.target.value) || 1)) })
              }
            />
          </label>
          <label>
            Semente
            <input value={sw.seed} onChange={(e) => set({ seed: Number(e.target.value) || 0 })} />
          </label>
          <label>
            Distribuição
            <select
              value={sw.distribution}
              onChange={(e) => set({ distribution: e.target.value as "gauss" })}
            >
              <option value="gauss">gaussiana (3σ = tolerância)</option>
              <option value="uniform">uniforme na faixa</option>
            </select>
          </label>
        </>
      )}
      {sw.kind === "worstcase" && (
        <>
          <label>
            Análise da medida
            <select
              value={measure.analysis}
              onChange={(e) => setMeasure({ analysis: e.target.value as AnalysisKind })}
            >
              <option value="op">.op</option>
              <option value="tran">.tran</option>
              <option value="ac">.ac</option>
              <option value="dc">.dc</option>
            </select>
          </label>
          <label>
            Sinal
            <input
              value={measure.vector}
              placeholder="v(out)"
              onChange={(e) => setMeasure({ vector: e.target.value })}
            />
          </label>
          <label>
            Medida
            <select
              value={measure.kind}
              onChange={(e) => setMeasure({ kind: e.target.value as MeasureKind })}
            >
              <option value="final">valor final / .op</option>
              <option value="mean">média</option>
              <option value="rms">RMS</option>
              <option value="max">máximo</option>
              <option value="min">mínimo</option>
              <option value="pp">pico a pico</option>
              <option value="at">valor em x</option>
              <option value="mag_db_at">módulo (dB) em f</option>
              <option value="phase_at">fase em f</option>
              <option value="frequency">frequência</option>
            </select>
          </label>
          <label>
            Em x / f
            <input
              value={measure.at ?? ""}
              onChange={(e) => setMeasure({ at: e.target.value || null })}
            />
          </label>
          <label>
            Janela: início
            <input
              value={measure.start ?? ""}
              onChange={(e) => setMeasure({ start: e.target.value || null })}
            />
          </label>
        </>
      )}
      <p className="small muted full">
        Monte Carlo e pior caso variam o campo “Tolerância” de resistores, capacitores, indutores e
        fontes, e a faixa do datasheet das peças do catálogo (V_Z do Zener, h_FE do BJT, V_GS(th) do
        MOSFET).
      </p>
    </div>
  );
}

function ParamsPanel({ sch, onChange }: { sch: Schematic; onChange: (s: Schematic) => void }) {
  const [text, setText] = useState(
    Object.entries(sch.params)
      .map(([k, v]) => `${k}=${v}`)
      .join("\n"),
  );
  useEffect(
    () =>
      setText(
        Object.entries(sch.params)
          .map(([k, v]) => `${k}=${v}`)
          .join("\n"),
      ),
    [sch.params],
  );
  return (
    <div className="param-grid">
      <label>
        Temperatura (°C)
        <input
          value={sch.temperature}
          onChange={(e) => onChange({ ...sch, temperature: e.target.value })}
        />
      </label>
      <label className="full">
        Parâmetros (.param), um por linha: nome=valor; use {"{nome}"} nos valores
        <textarea
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={() =>
            onChange({
              ...sch,
              params: Object.fromEntries(
                text
                  .split("\n")
                  .map((l) => l.split("="))
                  .filter((p): p is [string, string] => p.length === 2 && !!p[0]?.trim())
                  .map(([k, v]) => [k.trim(), v.trim()]),
              ),
            })
          }
        />
      </label>
      <label className="full">
        Diretivas SPICE (.model, .subckt de fabricante, .options, .ic, linhas sem símbolo)
        <textarea
          rows={8}
          value={sch.directives}
          onChange={(e) => onChange({ ...sch, directives: e.target.value })}
        />
      </label>
    </div>
  );
}

function SelectedPackage({
  view,
  packages,
}: {
  view: PartView | undefined;
  packages: PackageSpec[];
}) {
  if (!view) return null;
  const pkg = packages.find((p) => p.id === view.package);
  return (
    <div className="bb-symbol-package">
      <h3>Encapsulamento real</h3>
      {pkg && pkg.style !== "offboard" ? (
        <>
          <p className="small muted">{pkg.label}</p>
          <PackagePreview pkg={pkg} view={view} />
        </>
      ) : (
        <p className="small muted">
          {pkg ? `${pkg.label}: fora da protoboard.` : "Sem montagem física."}
        </p>
      )}
      <PinoutSource view={view} />
    </div>
  );
}

/** LEDs and lamps of the catalogue, plus nameplate presets of household lamps. */
function IndicatorPalette({
  parts,
  tool,
  onPick,
}: {
  parts: { led: PartOut[]; lamp: PartOut[] };
  tool: Tool;
  onPick: (t: Tool) => void;
}) {
  const active = (kind: string, id: string | null, params?: Record<string, string>) =>
    tool.kind === "place" &&
    tool.symbol === kind &&
    (tool.part_id ?? null) === id &&
    JSON.stringify(tool.params ?? {}) === JSON.stringify(params ?? {});
  const item = (kind: string, p: PartOut) => {
    const params: Record<string, string> = { part_label: p.part_number };
    if (p.colour && p.colour !== "ir") params.color = p.colour;
    return (
      <button
        key={p.id}
        className={active(kind, p.id, params) ? "palette-item active" : "palette-item"}
        title={`${p.manufacturer} ${p.part_number}${p.released ? "" : " (não revisado)"}`}
        onClick={() => onPick({ kind: "place", symbol: kind, part_id: p.id, params })}
      >
        {p.part_number}
        {p.summary ? <small className="muted"> · {p.summary}</small> : null}
      </button>
    );
  };
  return (
    <>
      {parts.led.length > 0 && <p className="small muted palette-sub">LEDs (catálogo)</p>}
      {parts.led.filter((p) => p.colour !== "ir").map((p) => item("led", p))}
      {parts.lamp.length > 0 && <p className="small muted palette-sub">Lâmpadas (catálogo)</p>}
      {[...parts.lamp]
        .sort((a, b) =>
          (a.summary ?? "").localeCompare(b.summary ?? "", "pt-BR", { numeric: true }),
        )
        .map((p) => item("lamp", p))}
      <p className="small muted palette-sub">Lâmpadas de rede (valor de placa)</p>
      {NAMEPLATE_LAMPS.map(([vn, pn]) => {
        const params = { vn, pn };
        return (
          <button
            key={`${vn}-${pn}`}
            className={active("lamp", null, params) ? "palette-item active" : "palette-item"}
            title="Lâmpada genérica pelos valores impressos no bulbo (sem ficha técnica)"
            onClick={() => onPick({ kind: "place", symbol: "lamp", params })}
          >
            {vn} V {pn} W
          </button>
        );
      })}
    </>
  );
}
