/** Typed client for the backend REST/WebSocket API (/api/v1). */

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
}
export type ComplexForm = "mag" | "mag_db" | "phase_deg" | "real" | "imag";

const BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
  measures: (id: string, plot: string, vector: string) =>
    request<Measurements>(
      `/simulations/${id}/plots/${encodeURIComponent(plot)}/measures?` +
        new URLSearchParams({ vector }),
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
  datasheets: DatasheetRef[];
  review: { status: string; reviewed_by: string | null; reviewed_at: string | null };
  notes: string[];
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
  yamlUrl: (id: string) => `${BASE}/components/${id}/yaml`,
  pageUrl: (sha: string, page: number) => `${BASE}/datasheets/${sha}/pages/${page}.png`,
  pdfUrl: (sha: string) => `${BASE}/datasheets/${sha}/pdf`,
  datasheet: (sha: string) => request<{ sha256: string; pages: number }>(`/datasheets/${sha}`),
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

export const bench = {
  diode: (body: DiodeBenchIn) =>
    request<DiodeBenchOut>("/devices/diode/iv", { method: "POST", body: JSON.stringify(body) }),
  zener: (body: ZenerBenchIn) =>
    request<ZenerBenchOut>("/devices/zener/iv", { method: "POST", body: JSON.stringify(body) }),
  bjt: (body: BjtBenchIn) =>
    request<CurvesOut>("/devices/bjt/output", { method: "POST", body: JSON.stringify(body) }),
  mosfet: (body: MosfetBenchIn) =>
    request<CurvesOut>("/devices/mosfet/output", { method: "POST", body: JSON.stringify(body) }),
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
  report: (id: string, body: DesignIn, simulate: boolean) =>
    postBlob(`/design/${id}/report.html?simulate=${simulate}`, body),
};
