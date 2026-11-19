// Breadboard geometry: the same rules as backend/src/circuitos/breadboard/board.py.
import type { BoardSpec, PackageSpec } from "./types";

export const P = 14; // pixels per 0.1" hole pitch
export const MX = 104; // includes the independent vertical power bus
export const MY = 28; // top margin
export const INSTRUMENT_H = 260; // area below the boards for complete instruments
export const BOARD_GAP = 22 * P;

/** Columns from top to bottom (rails and terminal strips). */
export const COLS = ["tp", "tn", "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "bn", "bp"];
const RAILS = new Set(["tp", "tn", "bn", "bp"]);
const UPPER = new Set(["a", "b", "c", "d", "e"]);

export interface Hole {
  col: string;
  row: number;
  board?: number;
}

export function parseHole(spec: BoardSpec, hole: string): Hole | null {
  const m = /^(2:)?(tp|tn|bn|bp|vp|vn|[a-j])(\d{1,2})$/.exec(hole.trim().toLowerCase());
  if (!m) return null;
  const col = m[2]!;
  const row = Number(m[3]);
  const board = m[1] ? 2 : 1;
  if (col === "vp" || col === "vn")
    return board === 1 && row >= 1 && row <= 40 ? { col, row, board } : null;
  if (RAILS.has(col)) return spec.rail_rows.includes(row) ? { col, row, board } : null;
  return row >= 1 && row <= spec.rows ? { col, row, board } : null;
}

export const holeName = (h: Hole) => `${h.board === 2 ? "2:" : ""}${h.col}${h.row}`;

export function holeXY(spec: BoardSpec, hole: string): [number, number] {
  const h = parseHole(spec, hole);
  if (!h) return [0, 0];
  if (h.col === "vp" || h.col === "vn") return [h.col === "vp" ? 24 : 52, MY + (h.row - 1) * P];
  return [MX + (h.row - 1) * P, MY + (spec.y[h.col] ?? 0) * P + (h.board === 2 ? BOARD_GAP : 0)];
}

export function boardSize(spec: BoardSpec): { w: number; h: number; boardH: number } {
  const boardH = MY * 2 + 17 * P + BOARD_GAP;
  return { w: MX * 2 + (spec.rows - 1) * P, h: boardH + INSTRUMENT_H, boardH };
}

/** Conductor of a hole: "12L", "12R" or the rail ("tn", or "tn-esq"/"tn-dir" when split). */
export function strip(spec: BoardSpec, hole: string, split = false): string {
  const h = parseHole(spec, hole);
  if (!h) return "";
  if (h.board === 2) return `2:${strip(spec, hole.slice(2), split)}`;
  if (h.col === "vp" || h.col === "vn") return h.col;
  if (RAILS.has(h.col))
    return split ? `${h.col}-${h.row <= spec.split_after ? "esq" : "dir"}` : h.col;
  return `${h.row}${UPPER.has(h.col) ? "L" : "R"}`;
}

export function allHoles(spec: BoardSpec): string[] {
  const out: string[] = [];
  for (const col of COLS) {
    const rows = RAILS.has(col)
      ? spec.rail_rows
      : Array.from({ length: spec.rows }, (_, i) => i + 1);
    for (const r of rows) out.push(`${col}${r}`);
  }
  return [
    ...out,
    ...out.map((h) => `2:${h}`),
    ...Array.from({ length: 40 }, (_, i) => [`vp${i + 1}`, `vn${i + 1}`]).flat(),
  ];
}

/** Nearest valid hole to a point, or null when the point is off the board. */
export function nearestHole(spec: BoardSpec, x: number, y: number): string | null {
  if (x < MX - 25) {
    const row = Math.round((y - MY) / P) + 1;
    const col = Math.abs(x - 24) < Math.abs(x - 52) ? "vp" : "vn";
    const h = `${col}${row}`;
    return Math.abs(x - (col === "vp" ? 24 : 52)) < P * 0.75 && parseHole(spec, h) ? h : null;
  }
  const second = y >= BOARD_GAP - 8;
  if (second) y -= BOARD_GAP;
  const row = Math.round((x - MX) / P) + 1;
  if (row < 1 || row > spec.rows) return null;
  let best: string | null = null;
  let dist = P * 0.75;
  for (const col of COLS) {
    const d = Math.abs(MY + (spec.y[col] ?? 0) * P - y);
    if (d < dist) {
      const name = `${second ? "2:" : ""}${col}${row}`;
      if (parseHole(spec, name)) {
        best = name;
        dist = d;
      }
    }
  }
  return best;
}

/** Shift a hole by rows and by columns (in COLS order); null if it falls off the board. */
export function shift(spec: BoardSpec, hole: string, dRow: number, dCol: number): string | null {
  const h = parseHole(spec, hole);
  if (!h) return null;
  const ci = COLS.indexOf(h.col) + dCol;
  if (ci < 0 || ci >= COLS.length) return null;
  const name = `${h.board === 2 ? "2:" : ""}${COLS[ci]}${h.row + dRow}`;
  return parseHole(spec, name) ? name : null;
}

export type Orientation = "h" | "v";

/** Legs of a package with leg 1 at `anchor`. DIP packages need leg 1 in column f, boards in h. */
export function placeLegs(
  spec: BoardSpec,
  pkg: PackageSpec,
  anchor: string,
  orient: Orientation,
): Record<string, string> | null {
  const a = parseHole(spec, anchor);
  if (!a) return null;
  const legs: Record<string, string> = {};
  if (pkg.style === "dip" || pkg.style === "board") {
    const [low, up] = pkg.cols ?? ["f", "e"];
    if (a.col !== low) return null;
    pkg.pins.forEach((pin, i) => {
      const [dr, dc] = pkg.offsets[i]!;
      legs[pin] = `${a.board === 2 ? "2:" : ""}${dc < 0 ? up : low}${a.row + dr}`;
    });
  } else {
    for (let i = 0; i < pkg.pins.length; i++) {
      const [dr] = pkg.offsets[i]!;
      const h = orient === "h" ? shift(spec, anchor, dr, 0) : shift(spec, anchor, 0, dr);
      if (!h) return null;
      legs[pkg.pins[i]!] = h;
    }
  }
  return Object.values(legs).every((h) => parseHole(spec, h)) ? legs : null;
}

export const WIRE_COLORS: Record<string, string> = {
  vermelho: "#d32f2f",
  preto: "#222",
  azul: "#1e63c6",
  verde: "#2e8b3c",
  amarelo: "#e2b100",
  laranja: "#ef7d18",
  branco: "#f4f4f4",
  cinza: "#8a8f96",
};

export const BAND_COLORS: Record<string, string> = {
  preto: "#1b1b1b",
  marrom: "#7a4a1d",
  vermelho: "#d0281c",
  laranja: "#f07f12",
  amarelo: "#f4d21f",
  verde: "#2c9a3e",
  azul: "#2357c7",
  violeta: "#8640b8",
  cinza: "#8d8d8d",
  branco: "#fafafa",
  ouro: "#c9a227",
  prata: "#bfc4c9",
};
