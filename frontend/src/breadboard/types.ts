// Breadboard view (Fase 10): the same shapes as backend/src/circuitos/breadboard.

export type WireColor =
  | "vermelho"
  | "preto"
  | "azul"
  | "verde"
  | "amarelo"
  | "laranja"
  | "branco"
  | "cinza";

export interface PlacedPart {
  ref: string;
  package: string;
  legs: Record<string, string>; // package pin (or terminal) -> hole
}

export interface Jumper {
  id: string;
  a: string;
  b: string;
  color: WireColor;
}

export interface Breadboard {
  board: "830";
  rails_split: boolean;
  parts: PlacedPart[];
  wires: Jumper[];
}

export interface BoardSpec {
  id: string;
  label: string;
  rows: number;
  upper: string;
  lower: string;
  rails: string[];
  rail_rows: number[];
  split_after: number;
  y: Record<string, number>;
  rail_polarity: Record<string, string>;
}

export interface PackageSpec {
  id: string;
  label: string;
  style: "axial" | "radial" | "inline" | "dip" | "offboard";
  pins: string[];
  pitch: number;
  span: number;
  min_span: number;
  body: string;
  note: string;
  offsets: [number, number][];
}

export interface Spec {
  board: BoardSpec;
  packages: PackageSpec[];
}

export interface PartView {
  ref: string;
  kind: string;
  package: string | null;
  origin: "datasheet" | "generico" | "sem_pinagem" | "sem_montagem" | "implicito";
  checkable: boolean;
  pinmap: Record<string, string>;
  labels: Record<string, string>;
  title: string;
  part_number: string | null;
  source: {
    document: string;
    page: number | null;
    location: string | null;
    url: string | null;
  } | null;
  status: string | null;
  notes: string[];
  bands: string[];
}

export interface ResolveOut {
  parts: PartView[];
  nets: Record<string, string>;
  net_labels: Record<string, string>;
  warnings: string[];
}

export type IssueKind =
  | "faltando"
  | "sobrando"
  | "trocada"
  | "nao_montado"
  | "furo"
  | "fora_do_esquematico"
  | "sem_pinagem"
  | "aviso";

export interface Issue {
  kind: IssueKind;
  message: string;
  refs: string[];
  holes: string[];
}

export interface CheckReport {
  ok: boolean;
  issues: Issue[];
  checked_parts: number;
  checked_legs: number;
  summary: string;
}

export interface Step {
  text: string;
  refs: string[];
  holes: string[];
}

export interface AutoOut {
  breadboard: Breadboard;
  notes: string[];
  report: CheckReport;
  guide: Step[];
}

export const emptyBreadboard = (): Breadboard => ({
  board: "830",
  rails_split: false,
  parts: [],
  wires: [],
});
