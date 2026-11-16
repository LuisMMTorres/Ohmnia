import type { Breadboard } from "../breadboard/types";
/** Schematic document and symbol library, mirroring backend circuitos/schematic/model.py. */

export type Point = [number, number];
export type Rotation = 0 | 90 | 180 | 270;

export interface Component {
  id: string;
  kind: string;
  ref: string;
  x: number;
  y: number;
  rot: Rotation;
  mirror: boolean;
  params: Record<string, string>;
  part_id: string | null;
}
export interface Wire {
  id: string;
  points: Point[];
}
export interface NetLabel {
  id: string;
  name: string;
  x: number;
  y: number;
}
export interface NetRef {
  at?: Point | null;
  net?: string | null;
  pin?: string | null;
}
export type ProbeKind = "v" | "vdiff" | "i" | "p";
export interface Probe {
  id: string;
  kind: ProbeKind;
  name?: string | null;
  target?: NetRef | null;
  reference?: NetRef | null;
  component?: string | null;
  pin?: string | null;
}
export type AnalysisKind = "op" | "tran" | "ac" | "dc" | "noise";
export interface Analysis {
  kind: AnalysisKind;
  params: Record<string, string>;
  enabled: boolean;
}
export type MeasureKind =
  | "final"
  | "mean"
  | "rms"
  | "max"
  | "min"
  | "pp"
  | "at"
  | "mag_db_at"
  | "phase_at"
  | "frequency";
export interface ScalarMeasure {
  analysis: AnalysisKind;
  vector: string;
  kind: MeasureKind;
  at?: string | null;
  start?: string | null;
  stop?: string | null;
}
export type SweepKind = "none" | "step" | "temp" | "montecarlo" | "worstcase";
export interface Sweep {
  kind: SweepKind;
  target?: string | null;
  spacing: "list" | "lin" | "dec" | "oct";
  values: string[];
  start?: string | null;
  stop?: string | null;
  step?: string | null;
  points?: number | null;
  runs: number;
  seed: number;
  distribution: "gauss" | "uniform";
  measure?: ScalarMeasure | null;
}
export interface Schematic {
  schema_version: string;
  title: string;
  components: Component[];
  wires: Wire[];
  labels: NetLabel[];
  probes: Probe[];
  analyses: Analysis[];
  sweep: Sweep;
  params: Record<string, string>;
  temperature: string;
  directives: string;
  breadboard?: Breadboard | null; // the same circuit on a breadboard (Fase 10)
}

export interface ParamDef {
  name: string;
  label: string;
  unit: string;
  default: string;
  type: "number" | "text" | "choice";
  choices: string[];
  optional: boolean;
  help: string;
}
export interface PinDef {
  name: string;
  dx: number;
  dy: number;
}
export interface SymbolDef {
  kind: string;
  label: string;
  group: string;
  prefix: string;
  pins: PinDef[];
  params: ParamDef[];
  catalogue: string[];
  tolerance: string | null;
  description: string;
}
export interface Library {
  symbols: SymbolDef[];
  analyses: Partial<Record<AnalysisKind, { label: string; params: ParamDef[] }>>;
}

export function emptySweep(): Sweep {
  return { kind: "none", spacing: "list", values: [], runs: 30, seed: 1, distribution: "gauss" };
}

export function emptySchematic(): Schematic {
  return {
    schema_version: "1",
    title: "Circuito sem título",
    components: [],
    wires: [],
    labels: [],
    probes: [],
    analyses: [{ kind: "tran", params: { tstop: "10m" }, enabled: true }],
    sweep: emptySweep(),
    params: {},
    temperature: "27",
    directives: "",
  };
}
