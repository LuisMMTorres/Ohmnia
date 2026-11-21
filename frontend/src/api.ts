/** Typed client for the backend REST/WebSocket API (/api/v1). */
import type {
  AutoOut,
  CheckReport,
  ResolveOut,
  Spec as BreadboardSpec,
  Step,
} from "./breadboard/types";
import type { Pinout } from "./breadboard/CataloguePinout";
import type { Library, ScalarMeasure, Schematic } from "./schematic/types";

export interface Quantity {
  value: number;
  unit: string;
}
export interface Vector {
  values: number[];
  unit: string;
}
export interface VectorInfo {
  name: string;
  unit: string;
  length: number;
  complex: boolean;
}
export interface PlotInfo {
  name: string;
  kind: "op" | "tran" | "ac" | "dc" | "noise" | "other";
  title: string;
  scale: string | null;
  vectors: VectorInfo[];
  run?: number;
  run_label?: string;
  base?: string;
}
export interface RunInfo {
  index: number;
  label: string;
  values: Record<string, string>;
}
export interface JobError {
  kind: string;
  message: string;
  suggestions: string[];
  log: string;
}
export interface Job {
  id: string;
  state: "queued" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  message: string;
  backend?: string | null;
  elapsed_s?: number | null;
  plots?: PlotInfo[] | null;
  error?: JobError | null;
  runs?: RunInfo[] | null;
  summary?: Record<string, unknown> | null;
  warnings?: string[] | null;
}
export interface PlotData {
  plot: string;
  kind: string;
  x: Vector | null;
  x_name: string | null;
  traces: Record<string, Vector>;
  decimated: boolean;
}
export interface Measurements {
  vector: string;
  mean: Quantity;
  rms: Quantity;
  peak: Quantity;
  peak_to_peak: Quantity;
  minimum: Quantity;
  maximum: Quantity;
  frequency?: Quantity | null;
  period?: Quantity | null;
  duty_cycle?: Quantity | null;
  base?: Quantity | null;
  top?: Quantity | null;
  rise_time?: Quantity | null;
  fall_time?: Quantity | null;
  overshoot?: Quantity | null;
  undershoot?: Quantity | null;
}
export type ComplexForm = "mag" | "mag_db" | "phase_deg" | "real" | "imag";

const BASE = "/api/v1";

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      /* body was not JSON */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return (await response.json()) as T;
}

export const api = {
  health: () =>
    request<{ status: string; version: string; simulator: Record<string, boolean> }>("/health"),
  submit: (netlist: string) =>
    request<Job>("/simulations", { method: "POST", body: JSON.stringify({ netlist }) }),
  status: (id: string) => request<Job>(`/simulations/${id}`),
  cancel: (id: string) => request<Job>(`/simulations/${id}`, { method: "DELETE" }),
  plot: (id: string, plot: string, vectors: string[], form: ComplexForm, maxPoints = 5000) =>
    request<PlotData>(
      `/simulations/${id}/plots/${encodeURIComponent(plot)}?` +
        new URLSearchParams({ vectors: vectors.join(","), form, max_points: String(maxPoints) }),
    ),
  measures: (id: string, plot: string, vector: string, start?: number, stop?: number) =>
    request<Measurements>(
      `/simulations/${id}/plots/${encodeURIComponent(plot)}/measures?` +
        new URLSearchParams({
          vector,
          ...(start !== undefined ? { start: String(start) } : {}),
          ...(stop !== undefined ? { stop: String(stop) } : {}),
        }),
    ),
};

/** Follow a job over WebSocket; falls back to polling if the socket fails. */
export function watchJob(id: string, onUpdate: (job: Job) => void): () => void {
  let stopped = false;
  let timer: number | undefined;
  const poll = async () => {
    if (stopped) return;
    try {
      const job = await api.status(id);
      onUpdate(job);
      if (job.state === "queued" || job.state === "running") timer = window.setTimeout(poll, 200);
    } catch {
      timer = window.setTimeout(poll, 500);
    }
  };
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}${BASE}/simulations/${id}/ws`);
  let finished = false;
  ws.onmessage = (event) => {
    const job = JSON.parse(event.data) as Job;
    if (job.state !== "queued" && job.state !== "running") finished = true;
    onUpdate(job);
  };
  ws.onerror = () => {
    if (!finished) void poll();
  };
  ws.onclose = () => {
    // The server closes after the final state; fetch the full status (with plots) once.
    if (!stopped) void poll();
  };
  return () => {
    stopped = true;
    window.clearTimeout(timer);
    ws.close();
  };
}

// ------------------------------------------------------------------ catalogue -----------

export type ParamStatus = "a_verificar" | "extraido" | "revisado";

export interface SourceRef {
  datasheet_id: string;
  page: number | null;
  location: string | null;
  excerpt: string | null;
  bbox?: [number, number, number, number] | null;
}
export interface Parameter {
  symbol: string;
  min: number | null;
  typ: number | null;
  max: number | null;
  unit: string;
  conditions: Record<string, Quantity>;
  source: SourceRef | null;
  status: ParamStatus;
  note: string | null;
}
export interface Attribute {
  value: string;
  source: SourceRef | null;
  status: ParamStatus;
  note: string | null;
}
export interface DatasheetRef {
  id: string;
  manufacturer: string;
  document_number: string | null;
  revision: string | null;
  url: string | null;
  sha256: string | null;
}
export interface ComponentRecord {
  id: string;
  category: string;
  manufacturer: string;
  part_number: string;
  family: string | null;
  package: string | null;
  lifecycle: string;
  parameters: Record<string, Parameter>;
  attributes?: Record<string, Attribute>;
  datasheets: DatasheetRef[];
  review: { status: string; reviewed_by: string | null; reviewed_at: string | null };
  notes: string[];
  curves: Curve[];
  spice_models: SpiceModel[];
  pinout?: Pinout | null; // breadboard view: package and pinout from the datasheet
}

export type AxisScale = "lin" | "log";
export interface AxisSpec {
  quantity: string;
  unit: string;
  scale: AxisScale;
}
export interface Curve {
  id: string;
  name: string;
  x: AxisSpec;
  y: AxisSpec;
  family: Record<string, Quantity>;
  points: [number, number][];
  source: SourceRef;
  method: "manual" | "vetor" | "cor";
  digitized_by: string;
  created_at: string;
}
export interface FitReport {
  curves: string[];
  quantity: string;
  points: number;
  rms_error_pct: number;
  max_error_pct: number;
  residuals: { x: number; measured: number; model: number; error_pct: number }[];
  simulated: boolean;
  assumptions: string[];
  params_origin: Record<string, string>;
}
export interface SpiceModel {
  id: string;
  name: string;
  kind: "model" | "subckt";
  device: string;
  pins: string[];
  params: Record<string, number>;
  text: string;
  origin: "fabricante" | "ajustado";
  source_note: string | null;
  checked: boolean;
  check_log: string | null;
  fit: FitReport | null;
}
export interface ParameterSpec {
  unit: string;
  kind: "max_rating" | "characteristic" | "thermal";
  description: string;
}
export interface ComponentDetail {
  record: ComponentRecord;
  schema_: {
    category: string;
    description: string;
    required: string[];
    parameters: Record<string, ParameterSpec>;
    attributes?: Record<string, string>;
  };
  release_blockers: string[];
}
export interface ComponentSummary {
  id: string;
  category: string;
  manufacturer: string;
  part_number: string;
  family: string | null;
  package: string | null;
  review_status: string;
  parameters_reviewed: number;
  parameters_total: number;
  highlights: Record<string, string>;
}

export interface CategoryReviewItem {
  id: string;
  manufacturer: string;
  part_number: string;
  before: string;
  after: string;
  marked: number;
  unsourced: string[];
  blockers: string[];
}
export interface CategoryReview {
  category: string;
  dry_run: boolean;
  items: CategoryReviewItem[];
  released: number;
  pending: number;
  already_released: number;
}

export const catalog = {
  list: (params: { category?: string; q?: string; status?: string; filters?: string[] }) => {
    const search = new URLSearchParams();
    if (params.category) search.set("category", params.category);
    if (params.q) search.set("q", params.q);
    if (params.status) search.set("status", params.status);
    for (const f of params.filters ?? []) search.append("filter", f);
    return request<ComponentSummary[]>(`/components?${search}`);
  },
  stats: () => request<Record<string, number>>("/components/stats"),
  get: (id: string) => request<ComponentDetail>(`/components/${id}`),
  review: (id: string, key: string, status: ParamStatus, note?: string) =>
    request<ComponentDetail>(`/components/${id}/parameters/${encodeURIComponent(key)}/review`, {
      method: "POST",
      body: JSON.stringify({ status, note }),
    }),
  release: (id: string, reviewer: string) =>
    request<ComponentDetail>(`/components/${id}/release`, {
      method: "POST",
      body: JSON.stringify({ reviewer }),
    }),
  reviewCategory: (category: string, reviewer: string, dryRun: boolean) =>
    request<CategoryReview>("/components/review-category", {
      method: "POST",
      body: JSON.stringify({ category, reviewer, dry_run: dryRun }),
    }),
  /** Review and release the given parts (those of one circuit); dryRun only previews. */
  reviewParts: (ids: string[], reviewer: string, dryRun: boolean) =>
    request<Omit<CategoryReview, "category" | "already_released">>("/components/review-parts", {
      method: "POST",
      body: JSON.stringify({ ids, reviewer, dry_run: dryRun }),
    }),
  yamlUrl: (id: string) => `${BASE}/components/${id}/yaml`,
  pageUrl: (sha: string, page: number) => `${BASE}/datasheets/${sha}/pages/${page}.png`,
  pdfUrl: (sha: string) => `${BASE}/datasheets/${sha}/pdf`,
  datasheet: (sha: string) => request<{ sha256: string; pages: number }>(`/datasheets/${sha}`),
};

// --------------------------------------------------------------- datasheet import -------

export type Bbox = [number, number, number, number];
export type ImportMethod = "regras" | "llm" | "manual";
export interface Candidate {
  key: string;
  symbol: string;
  min: number | null;
  typ: number | null;
  max: number | null;
  unit: string;
  conditions: Record<string, Quantity>;
  conditions_text: string | null;
  page: number;
  bbox: Bbox | null;
  excerpt: string;
  method: ImportMethod;
  confidence: number;
  notes: string[];
  accepted: boolean;
}
export interface ImportMeta {
  manufacturer: string;
  part_number: string;
  category: string;
  package: string | null;
  family: string | null;
  document_number: string | null;
  revision: string | null;
  url: string | null;
}
export interface CategoryScore {
  category: string;
  score: number;
  found: string[];
}
export interface RejectedProposal {
  proposal: {
    key: string;
    min: number | null;
    typ: number | null;
    max: number | null;
    unit: string;
    page: number;
    excerpt: string;
  };
  reason: string;
}
export interface ImportJob {
  id: string;
  sha256: string;
  filename: string;
  pages: number;
  status: "extraido" | "importado" | "descartado";
  meta: ImportMeta;
  ranking: CategoryScore[];
  candidates: Candidate[];
  rejected: RejectedProposal[];
  ocr_pages: number[];
  warnings: string[];
  llm_model: string | null;
  component_id: string | null;
  created_at: string;
  updated_at: string;
}
export interface QueueItem {
  index: number;
  grupo: string;
  arquivo: string;
  part_number: string;
  fabricante: string;
  tipo: "peça" | "série";
  categoria: string | null;
  sem_categoria: string | null;
  url: string | null;
  link: {
    situacao: "ok" | "bloqueado" | "quebrado" | "indisponivel";
    verificado_em: string;
    nota: string;
  } | null;
  local: { caminho: string; sha256: string; situacao: "ok" | "invalido"; nota: string } | null;
  importable: boolean;
  no_catalogo: string[];
}
export interface ImportSummary {
  id: string;
  filename: string;
  status: ImportJob["status"];
  part_number: string;
  category: string;
  candidates: number;
  accepted: number;
  updated_at: string;
}
export interface Capabilities {
  ocr: boolean;
  llm: { available: boolean; model: string; reason: string | null };
}
export interface PageText {
  page: number;
  width: number;
  height: number;
  ocr: boolean;
  rows: { text: string; bbox: Bbox }[];
}
export interface AxisCalibration {
  p1: number;
  v1: number;
  p2: number;
  v2: number;
  scale: AxisScale;
}
export interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}
export interface VectorPath {
  index: number;
  colour: [number, number, number] | null;
  width: number | null;
  points: [number, number][];
  bbox: Bbox;
}
export interface CurveIn {
  name: string;
  x: AxisSpec;
  y: AxisSpec;
  family: Record<string, Quantity>;
  calibration: { x: AxisCalibration; y: AxisCalibration };
  positions: [number, number][];
  datasheet_id: string;
  page: number;
  location?: string | null;
  bbox?: Bbox | null;
  method: Curve["method"];
  digitized_by: string;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const imports = {
  capabilities: () => request<Capabilities>("/imports/capabilities"),
  upload: async (file: File) => {
    const response = await fetch(`${BASE}/datasheets?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/pdf" },
      body: file,
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        detail = (await response.json()).detail ?? detail;
      } catch {
        /* not JSON */
      }
      throw new Error(String(detail));
    }
    return (await response.json()) as { sha256: string; pages: number; filename: string };
  },
  start: (body: {
    sha256: string;
    filename: string;
    meta: Partial<ImportMeta>;
    use_llm: boolean;
  }) => post<ImportJob>("/imports", body),
  list: () => request<ImportSummary[]>("/imports"),
  get: (id: string) => request<ImportJob>(`/imports/${id}`),
  save: (id: string, meta: ImportMeta, candidates: Candidate[]) =>
    request<ImportJob>(`/imports/${id}`, {
      method: "PUT",
      body: JSON.stringify({ meta, candidates }),
    }),
  remap: (id: string, meta: ImportMeta, use_llm: boolean) =>
    post<ImportJob>(`/imports/${id}/remap`, { meta, use_llm }),
  commit: (id: string, created_by: string, replace = false) =>
    post<ComponentDetail>(`/imports/${id}/commit`, { created_by, replace }),
  discard: (id: string) => request<ImportJob>(`/imports/${id}`, { method: "DELETE" }),
  pageText: (sha: string, page: number) =>
    request<PageText>(`/datasheets/${sha}/pages/${page}/text`),
  vectorPaths: (sha: string, page: number, rect: Rect) =>
    post<VectorPath[]>(`/datasheets/${sha}/pages/${page}/vector-paths`, rect),
  trace: (
    sha: string,
    page: number,
    rect: Rect,
    colour: [number, number, number],
    tolerance = 60,
  ) =>
    post<[number, number][]>(`/datasheets/${sha}/pages/${page}/trace`, { rect, colour, tolerance }),
  queue: () => request<QueueItem[]>("/datasheet-queue"),
  importQueued: (index: number, use_llm: boolean) =>
    post<ImportJob>(`/datasheet-queue/${index}/import`, { use_llm }),
  addCurve: (componentId: string, body: CurveIn) =>
    post<ComponentDetail>(`/components/${componentId}/curves`, body),
  deleteCurve: (componentId: string, curveId: string) =>
    request<ComponentDetail>(`/components/${componentId}/curves/${curveId}`, { method: "DELETE" }),
  importModels: (componentId: string, text: string, source_note: string | null) =>
    post<ComponentDetail>(`/components/${componentId}/spice-models/import`, { text, source_note }),
  fitModel: (componentId: string, curve_ids: string[], name?: string) =>
    post<ComponentDetail>(`/components/${componentId}/spice-models/fit`, { curve_ids, name }),
  deleteModel: (componentId: string, modelId: string) =>
    request<ComponentDetail>(`/components/${componentId}/spice-models/${modelId}`, {
      method: "DELETE",
    }),
};

// --------------------------------------------------------------------- bench ------------

export interface DiodeBenchIn {
  model: { Is: Quantity; n: number; Rs: Quantity };
  temperatures: Quantity[];
  v_min: Quantity;
  v_max: Quantity;
  points?: number;
  component_id?: string | null;
}
export interface CalcStep {
  id: string;
  description: string;
  latex: string;
  inputs: Record<string, Quantity>;
  output: Quantity;
  assumptions: string[];
}
export interface DiodeBenchOut {
  v: Vector;
  curves: Record<string, Vector>;
  markers: {
    key: string;
    label: string;
    v: Quantity;
    i: Quantity;
    temperature: Quantity | null;
    reviewed: boolean;
  }[];
  steps: CalcStep[];
  spice_model: string;
  warnings: string[];
}

export interface ZenerModel {
  VZ0: Quantity;
  Rz: Quantity;
  Is_r: Quantity;
  n_r: number;
  TC: Quantity;
  forward: { Is: Quantity; n: number; Rs: Quantity };
}
export interface ZenerBenchIn {
  model: ZenerModel;
  temperatures: Quantity[];
  v_max?: Quantity | null;
  points?: number;
  component_id?: string | null;
  fit?: boolean;
  iz_op?: Quantity | null;
}
export type ZenerBenchOut = Omit<DiodeBenchOut, "spice_model"> & {
  model: ZenerModel;
  spice_model: string;
};

export interface CurvesOut {
  x: Vector;
  curves: Record<string, Vector>;
  markers: DiodeBenchOut["markers"];
  steps: CalcStep[];
  model: Record<string, Quantity | number>;
  spice_model: string;
  warnings: string[];
}
export interface BjtBenchIn {
  model: { IS: Quantity; BF: number; BR: number; VAF: Quantity };
  ib: Quantity[];
  vce_max: Quantity;
  component_id?: string | null;
  fit?: boolean;
}
export interface MosfetBenchIn {
  model: { VTO: Quantity; KP: Quantity; LAMBDA: Quantity };
  vgs: Quantity[];
  vds_max: Quantity;
  component_id?: string | null;
  fit?: boolean;
}

export interface IgbtBenchIn {
  model: { VT: Quantity; V0: Quantity; R_on: Quantity; K: Quantity };
  vge: Quantity[];
  vce_max: Quantity;
  losses: { VCC: Quantity; IC: Quantity; fs: Quantity; D: number };
  component_id?: string | null;
  fit?: boolean;
}

export interface ThyristorBenchIn {
  model: {
    kind: "scr" | "triac";
    VT0: Quantity;
    rT: Quantity;
    IGT: Quantity[];
    IH: Quantity;
    IL: Quantity;
  };
  drive: {
    Vm: Quantity;
    f: Quantity;
    R: Quantity;
    alpha: Quantity;
    IG: Quantity;
    tw: Quantity;
    gate_mode: "positivo" | "negativo" | "acompanha";
  };
  component_id?: string | null;
  fit?: boolean;
}
export interface WaveOut {
  t: Vector;
  traces: Record<string, Vector>;
  events: { kind: string; t_ms: number }[];
  summary: { Vavg: Quantity; Vrms: Quantity; conduction: Quantity };
  steps: CalcStep[];
  model: Record<string, Quantity | string>;
  spice_model: string;
  warnings: string[];
}

export interface PnBenchIn {
  NA: Quantity;
  ND: Quantity;
  area: Quantity;
  Dn: Quantity;
  Dp: Quantity;
  Ln: Quantity;
  Lp: Quantity;
  B: Quantity;
  Eg: Quantity;
  eps_r: number;
  T: Quantity;
  vr: Quantity;
  vr_max: Quantity;
}
export interface PnOut {
  vr: Vector;
  depletion: Record<string, Vector>;
  field: Vector;
  capacitance: Vector;
  temperature: Vector;
  ni: Vector;
  v: Vector;
  current: Vector;
  steps: CalcStep[];
  spice_model: string;
  warnings: string[];
}

export interface OpampBenchIn {
  model: {
    A0: number;
    GBW: Quantity;
    SR: Quantity;
    Vos: Quantity;
    Ib: Quantity;
    Ios: Quantity;
    Rin: Quantity;
    CMRR_db: number;
    PSRR_db: number;
    drop: Quantity;
  };
  VS: Quantity;
  component_id: string | null;
}

export interface BenchTestOut {
  id: string;
  name: string;
  measured: Quantity;
  expected: Quantity;
  error_pct: number;
  tolerance_pct: number;
  ok: boolean;
  method: string;
}

export interface OpampBenchOut {
  tests: BenchTestOut[];
  bode_f: Vector;
  bode_mag_db: Vector;
  bode_phase: Vector;
  step_t: Vector;
  step_in: Vector;
  step_out: Vector;
  steps: CalcStep[];
  model: Record<string, Quantity | string>;
  netlists: Record<string, string>;
  warnings: string[];
}

export interface PeripheralParam {
  name: string;
  label: string;
  unit: string;
  default: string;
  type: string;
  choices: string[];
  help: string;
}

export interface PeripheralBenchInfo {
  kind: string;
  label: string;
  group: string;
  summary: string;
  description: string;
  tests: string[];
  params: PeripheralParam[];
  fixture: PeripheralParam[];
  catalogue: string[];
  seconds: number;
}

export interface PeripheralPart {
  id: string;
  part_number: string;
  manufacturer: string;
  status: string;
}

export interface PeripheralBenchIn {
  params: Record<string, string>;
  fixture: Record<string, string>;
  component_id: string | null;
}

export interface PeripheralCurve {
  id: string;
  title: string;
  x_label: string;
  x_unit: string;
  x: number[];
  traces: { name: string; unit: string; values: (number | null)[] }[];
  x_log: boolean;
}

export interface PeripheralBenchOut {
  kind: string;
  tests: BenchTestOut[];
  curves: PeripheralCurve[];
  steps: CalcStep[];
  netlists: Record<string, string>;
  warnings: string[];
  used: Record<string, string>;
}

export const bench = {
  diode: (body: DiodeBenchIn) =>
    request<DiodeBenchOut>("/devices/diode/iv", { method: "POST", body: JSON.stringify(body) }),
  zener: (body: ZenerBenchIn) =>
    request<ZenerBenchOut>("/devices/zener/iv", { method: "POST", body: JSON.stringify(body) }),
  bjt: (body: BjtBenchIn) =>
    request<CurvesOut>("/devices/bjt/output", { method: "POST", body: JSON.stringify(body) }),
  mosfet: (body: MosfetBenchIn) =>
    request<CurvesOut>("/devices/mosfet/output", { method: "POST", body: JSON.stringify(body) }),
  igbt: (body: IgbtBenchIn) =>
    request<CurvesOut>("/devices/igbt/output", { method: "POST", body: JSON.stringify(body) }),
  pn: (body: PnBenchIn) =>
    request<PnOut>("/devices/pn", { method: "POST", body: JSON.stringify(body) }),
  thyristor: (body: ThyristorBenchIn) =>
    request<WaveOut>("/devices/thyristor/waveform", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  opamp: (body: OpampBenchIn) =>
    request<OpampBenchOut>("/devices/opamp/bench", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  peripherals: () => request<PeripheralBenchInfo[]>("/devices/peripherals"),
  peripheralParts: (kind: string) =>
    request<PeripheralPart[]>(`/devices/peripherals/${encodeURIComponent(kind)}/parts`),
  peripheral: (kind: string, body: PeripheralBenchIn) =>
    request<PeripheralBenchOut>(`/devices/peripherals/${encodeURIComponent(kind)}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ------------------------------------------------------------------ design ---------------

export interface DesignModuleInfo {
  id: string;
  title: string;
  family: string;
  defaults: Record<string, unknown>;
  json_schema: JsonSchema;
  spec_labels: Record<string, string>;
  enum_labels: Record<string, string>;
  summary_labels: Record<string, string>;
}
export interface JsonSchema {
  type?: string;
  properties?: Record<string, JsonSchema>;
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  enum?: (string | number)[];
  const?: string | number;
  anyOf?: JsonSchema[];
  default?: unknown;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  title?: string;
  description?: string;
}
export type Policy = "didatico" | "industrial";
export interface DesignIn {
  spec: Record<string, unknown>;
  policy: Policy;
  locks: Record<string, string>;
  costs?: Record<string, number>;
  project?: string | null;
  /** Element → new value typed on the schematic (the simulation runs the edited circuit). */
  overrides?: Record<string, string>;
  /** Waveforms added by clicking the schematic (simulation only). */
  probes?: UserProbe[];
}
export interface Role {
  designator: string;
  category: string;
  description: string;
  count: number;
}
export interface Choice {
  designator: string;
  component_id: string;
  part_number: string;
  manufacturer: string;
  locked: boolean;
  released: boolean;
}
export type MarginStatus = "ok" | "atencao" | "violado";
export interface MarginCheck {
  designator: string;
  parameter: string;
  stress: Quantity;
  rating: Quantity;
  required_factor: number;
  margin_pct: number;
  status: MarginStatus;
  note: string | null;
}
export interface ThermalResult {
  designator: string;
  power: Quantity;
  Tj: Quantity;
  Tj_max: Quantity;
  path: string;
  required_Rsa: Quantity | null;
  status: MarginStatus;
  heatsink: string | null;
  heatsink_id: string | null;
  heatsink_manufacturer: string | null;
  heatsink_Rsa: Quantity | null;
}
export interface DesignWarning {
  code: string;
  message: string;
  /** Parts of this circuit waiting for review that would settle the warning. */
  parts?: string[];
}
export interface SimComparison {
  quantity: string;
  analytic: Quantity;
  simulated: Quantity;
  error_pct: number;
  tolerance_pct: number;
  ok: boolean;
}
export interface DesignResult {
  module_id: string;
  steps: CalcStep[];
  roles: Role[];
  selection: Choice[];
  margins: MarginCheck[];
  thermal: ThermalResult[];
  summary: Record<string, Quantity>;
  iterations: number;
  converged: boolean;
  warnings: DesignWarning[];
  traces: Record<string, Vector>;
  /** Time span of the traces; null: one period of spec.f. */
  trace_period?: Quantity | null;
  /** Frequency response: log-spaced frequencies (Hz) and |H| per label. */
  bode_f?: Vector | null;
  bode?: Record<string, Vector>;
}
export interface CandidateOut {
  id: string;
  part_number: string;
  manufacturer: string;
  released: boolean;
}
export interface DesignOut {
  result: DesignResult;
  netlist: string;
  options: Record<string, CandidateOut[]>;
}
export interface SimulateOut {
  comparisons: SimComparison[];
  t_ms: number[];
  traces: Record<string, Vector>;
  ok: boolean;
  bode_f?: number[];
  bode?: Record<string, Vector>;
  /** Peak, mean and RMS of every probe; S, P, Q, D and power factor of every port (ngspice). */
  measurements?: Measurements | null;
  /** Values were changed on the schematic: the analytic results describe the original design. */
  edited?: boolean;
}
export interface UserProbe {
  kind: "v" | "vdiff" | "i" | "p";
  a: string;
  b?: string | null;
  pin?: number;
}
export interface WaveMeasure {
  label: string;
  unit: string;
  peak: Quantity;
  max: Quantity;
  min: Quantity;
  avg: Quantity;
  rms: Quantity;
}
export interface PowerMeasure {
  label: string;
  V_rms: Quantity;
  I_rms: Quantity;
  S: Quantity;
  P: Quantity;
  Q: Quantity;
  D: Quantity;
  PF: Quantity;
  DPF: Quantity;
}
export interface Measurements {
  waves: WaveMeasure[];
  powers: PowerMeasure[];
}
/** Element of the simulated circuit of a design (values editable, probes on its terminals). */
export interface CircuitElement {
  name: string;
  letter: string;
  nodes: string[];
  pins: string[];
  value: string;
  edit: "value" | "source" | "none";
  sense: boolean;
  role: string | null;
  original: string | null;
}

async function postBlob(path: string, body: unknown): Promise<Blob> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      /* body was not JSON */
    }
    throw new Error(String(detail));
  }
  return response.blob();
}

export const design = {
  modules: () => request<DesignModuleInfo[]>("/design/modules"),
  run: (id: string, body: DesignIn) =>
    request<DesignOut>(`/design/${id}`, { method: "POST", body: JSON.stringify(body) }),
  simulate: (id: string, body: DesignIn) =>
    request<SimulateOut>(`/design/${id}/simulate`, { method: "POST", body: JSON.stringify(body) }),
  schematic: (id: string, body: DesignIn) => postBlob(`/design/${id}/schematic.svg`, body),
  bom: (id: string, body: DesignIn) => postBlob(`/design/${id}/bom.csv`, body),
  bomFile: (id: string, body: DesignIn, fmt: "csv" | "xlsx" | "pdf") =>
    postBlob(`/design/${id}/bom.${fmt}`, body),
  bomLines: (id: string, body: DesignIn) =>
    request<BomOut>(`/design/${id}/bom`, { method: "POST", body: JSON.stringify(body) }),
  report: (id: string, body: DesignIn, simulate: boolean) =>
    postBlob(`/design/${id}/report.html?simulate=${simulate}`, body),
  reportPdf: (id: string, body: DesignIn, simulate: boolean) =>
    postBlob(`/design/${id}/report.pdf?simulate=${simulate}`, body),
  kicad: (id: string, body: DesignIn) => postBlob(`/design/${id}/kicad.net`, body),
  elements: (id: string, body: DesignIn) =>
    request<{ elements: CircuitElement[]; nodes: string[] }>(`/design/${id}/elements`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export interface BomLine {
  designator: string;
  designators: string[];
  quantity: number;
  description: string;
  part_number: string;
  manufacturer: string;
  value: string;
  note: string;
  parameter: string;
  stress: string;
  rating: string;
  margin_pct: number | null;
  margin_status: string;
  tj: string;
  tj_max: string;
  heatsink: string;
  datasheet: string | null;
  unit_cost: number | null;
  total_cost: number | null;
  cost_key: string;
}
export interface BomOut {
  title: string;
  lines: BomLine[];
  total_cost: number | null;
}

// ---------------------------------------------------------------------- projects ------

export interface Revision {
  number: number;
  saved_at: string;
  spec: Record<string, unknown>;
  policy: Policy;
  locks: Record<string, string>;
  costs: Record<string, number>;
  note: string | null;
  schematic?: import("./schematic/types").Schematic | null;
}
export interface ProjectDocument {
  format: "circuitos-projeto";
  format_version: number;
  id: string;
  name: string;
  module_id: string;
  description: string;
  created_at: string;
  updated_at: string;
  current: Revision;
  history: Revision[];
}
export interface ProjectSummary {
  id: string;
  name: string;
  module_id: string;
  revision: number;
  updated_at: string;
}
interface ProjectContent {
  spec: Record<string, unknown>;
  policy: Policy;
  locks: Record<string, string>;
  costs: Record<string, number>;
  note?: string | null;
  schematic?: import("./schematic/types").Schematic | null;
}

export const projects = {
  list: () => request<ProjectSummary[]>("/projects"),
  get: (id: string) => request<ProjectDocument>(`/projects/${id}`),
  create: (name: string, module_id: string, content: ProjectContent) =>
    request<ProjectDocument>("/projects", {
      method: "POST",
      body: JSON.stringify({ name, module_id, ...content }),
    }),
  save: (id: string, content: ProjectContent & { name?: string }) =>
    request<ProjectDocument>(`/projects/${id}`, { method: "PUT", body: JSON.stringify(content) }),
  restore: (id: string, n: number) =>
    request<ProjectDocument>(`/projects/${id}/restore/${n}`, { method: "POST" }),
  duplicate: (id: string, name?: string) =>
    request<ProjectDocument>(`/projects/${id}/duplicate`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  remove: (id: string) => request<{ status: string }>(`/projects/${id}`, { method: "DELETE" }),
  fileUrl: (id: string) => `${BASE}/projects/${id}/file`,
  importFile: (text: string) =>
    request<ProjectDocument>("/projects/import", { method: "POST", body: text }),
};

// ------------------------------------------------------------------- schematic simulator

/** A rating of a part (catalogue or typed by the user), checked after the simulation. */
export interface LimitOut {
  ref: string;
  quantity: "V" | "I" | "P" | "T";
  name: string;
  limit: number;
  unit: string;
  measure: "peak" | "mean" | "rms" | "peak_abs";
  v_pos?: string | null;
  v_neg?: string | null;
  current?: string | null;
  current_sign?: number;
  resistance?: number | null;
  rth?: number | null;
  t_amb?: number | null;
  source?: string;
  advice?: string;
  reviewed?: boolean;
}

/** A rating exceeded in the simulation: the part would burn or be damaged. */
export interface DamageOut {
  ref: string;
  quantity: "V" | "I" | "P" | "T";
  name: string;
  value: number;
  limit: number;
  unit: string;
  cause: string;
  advice: string;
  source: string;
  reviewed: boolean;
}

export interface NetlistOut {
  indicators?: Record<string, IndicatorOut>;
  limits?: LimitOut[];
  netlist: string;
  nets: Record<string, string[]>;
  probes: { name: string; expr: string; unit: string; probe_id: string | null }[];
  warnings: string[];
  spreads: {
    component: string;
    param: string;
    low: number;
    nominal: number;
    high: number;
    source: string;
  }[];
  steps: unknown[];
}
export interface PartOut {
  id: string;
  part_number: string;
  manufacturer: string;
  category: string;
  released: boolean;
  status: string;
  summary?: string;
  colour?: string | null;
}
/** LED or lamp of the netlist: current vector and the values that give its brightness. */
export interface IndicatorOut {
  kind: "led" | "lamp";
  vector: string;
  i_ref?: number | null;
  i_max?: number | null;
  colour?: string | null;
  r?: number | null;
  p_nom?: number | null;
  v_nom?: number | null;
}
export interface SpectrumOut {
  vector: string;
  unit: string;
  f0: number;
  window_start: number;
  window_stop: number;
  frequency: Vector;
  amplitude: Vector;
  harmonics: { k: number; frequency: number; amplitude: number; percent: number }[];
  thd: number;
  rms: number;
  dc: number;
}
export interface StatisticsOut {
  measure: ScalarMeasure;
  unit: string;
  values: { run: number; label: string; value: number | null; error: string | null }[];
  stats: { mean: number; std: number; min: number; max: number; [k: string]: number };
  nominal: number | null;
  histogram: { edges: number[]; counts: number[] };
}
export interface FigureIn {
  plot: string;
  vectors: string[];
  kind: "time" | "xy" | "bode" | "spectrum";
  format: "svg" | "png" | "pdf";
  title?: string;
  x_vector?: string | null;
  all_runs?: boolean;
  start?: number | null;
  stop?: number | null;
  f0?: number | null;
  periods?: number;
}

const plotPath = (id: string, plot: string) =>
  `/simulations/${id}/plots/${encodeURIComponent(plot)}`;

export const schematicApi = {
  library: () => request<Library>("/schematic/library"),
  examples: () =>
    request<{ name: string; description: string; schematic: Schematic }[]>("/schematic/examples"),
  parts: (kind: string) => request<PartOut[]>(`/schematic/parts?kind=${encodeURIComponent(kind)}`),
  netlist: (schematic: Schematic) =>
    request<NetlistOut>("/schematic/netlist", {
      method: "POST",
      body: JSON.stringify({ schematic }),
    }),
  damage: (job_id: string, limits: LimitOut[]) =>
    request<DamageOut[]>("/schematic/damage", {
      method: "POST",
      body: JSON.stringify({ job_id, limits }),
    }),
  kicad: (schematic: Schematic) => postBlob("/schematic/kicad.net", { schematic }),
  importNetlist: (netlist: string) =>
    request<{ schematic: Schematic; warnings: string[] }>("/schematic/import", {
      method: "POST",
      body: JSON.stringify({ netlist }),
    }),
  simulate: (schematic: Schematic) =>
    request<{ job_id: string; netlist: string; runs: number; warnings: string[] }>(
      "/schematic/simulate",
      { method: "POST", body: JSON.stringify({ schematic }) },
    ),
  spectrum: (id: string, plot: string, params: Record<string, string>) =>
    request<SpectrumOut>(`${plotPath(id, plot)}/spectrum?` + new URLSearchParams(params)),
  statistics: (id: string, params: Record<string, string>) =>
    request<StatisticsOut>(`/simulations/${id}/statistics?` + new URLSearchParams(params)),
  expression: (id: string, plot: string, expr: string, name?: string) =>
    request<VectorInfo>(`${plotPath(id, plot)}/expressions`, {
      method: "POST",
      body: JSON.stringify({ expr, name: name || null, all_runs: true }),
    }),
  csvUrl: (id: string, plot: string, vectors: string[], form: ComplexForm) =>
    `${BASE}${plotPath(id, plot)}/csv?` + new URLSearchParams({ vectors: vectors.join(","), form }),
  figure: (id: string, body: FigureIn) => postBlob(`/simulations/${id}/figure`, body),
};

export function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------------------- breadboard

export const breadboardApi = {
  spec: () => request<BreadboardSpec>("/breadboard/spec"),
  resolve: (schematic: Schematic) =>
    request<ResolveOut>("/breadboard/resolve", {
      method: "POST",
      body: JSON.stringify({ schematic }),
    }),
  auto: (schematic: Schematic) =>
    request<AutoOut>("/breadboard/auto", { method: "POST", body: JSON.stringify({ schematic }) }),
  check: (schematic: Schematic) =>
    request<CheckReport>("/breadboard/check", {
      method: "POST",
      body: JSON.stringify({ schematic }),
    }),
  guide: (schematic: Schematic) =>
    request<Step[]>("/breadboard/guide", { method: "POST", body: JSON.stringify({ schematic }) }),
};
