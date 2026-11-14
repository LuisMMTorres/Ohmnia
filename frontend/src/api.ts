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
