// Editing jumper wires and bench-instrument leads already on the board: move one end to
// another hole, drag the whole wire, take it out. Pure functions so the view and the tests
// share the same rules (one conductor per hole, both ends on real holes).

import { holeXY, nearestHole } from "./geometry";
import type { BoardSpec, Breadboard, Jumper } from "./types";

/** What is being edited: a jumper wire, or the lead of an off-board instrument terminal. */
export type WireRef =
  | { kind: "wire"; id: string }
  | { kind: "lead"; ref: string; terminal: string };

/** Holes taken by parts, leads and wires, leaving out the item being edited. */
export function occupiedExcept(bb: Breadboard, item: WireRef | null): Set<string> {
  const taken = new Set<string>();
  for (const p of bb.parts)
    for (const [pin, h] of Object.entries(p.legs))
      if (!(item?.kind === "lead" && item.ref === p.ref && item.terminal === pin)) taken.add(h);
  for (const w of bb.wires)
    if (!(item?.kind === "wire" && item.id === w.id)) {
      taken.add(w.a);
      taken.add(w.b);
    }
  return taken;
}

/** The wire with one end moved to `hole`, or null when that hole cannot take it. */
export function moveWireEnd(
  bb: Breadboard,
  id: string,
  end: "a" | "b",
  hole: string,
): Jumper | null {
  const w = bb.wires.find((x) => x.id === id);
  if (!w) return null;
  const other = end === "a" ? w.b : w.a;
  if (hole === other || occupiedExcept(bb, { kind: "wire", id }).has(hole)) return null;
  return { ...w, [end]: hole };
}

/**
 * The whole wire carried by (dx, dy) pixels, each end snapped to the nearest hole: the wire
 * keeps its shape on the board and may cross to the rails, the other board or the power bus.
 */
export function moveWire(
  spec: BoardSpec,
  bb: Breadboard,
  id: string,
  dx: number,
  dy: number,
): Jumper | null {
  const w = bb.wires.find((x) => x.id === id);
  if (!w) return null;
  const snap = (h: string) => {
    const [x, y] = holeXY(spec, h);
    return nearestHole(spec, x + dx, y + dy);
  };
  const a = snap(w.a);
  const b = snap(w.b);
  if (!a || !b || a === b) return null;
  const taken = occupiedExcept(bb, { kind: "wire", id });
  if (taken.has(a) || taken.has(b)) return null;
  return { ...w, a, b };
}

/** The board with an instrument lead clipped to another hole, or null if that hole is taken. */
export function moveLead(
  bb: Breadboard,
  ref: string,
  terminal: string,
  hole: string,
): Breadboard | null {
  if (occupiedExcept(bb, { kind: "lead", ref, terminal }).has(hole)) return null;
  return {
    ...bb,
    parts: bb.parts.map((p) =>
      p.ref === ref ? { ...p, legs: { ...p.legs, [terminal]: hole } } : p,
    ),
  };
}

/** The board without that wire, or with that instrument lead unclipped. */
export function removeWire(bb: Breadboard, item: WireRef): Breadboard {
  if (item.kind === "wire") return { ...bb, wires: bb.wires.filter((w) => w.id !== item.id) };
  return {
    ...bb,
    parts: bb.parts.map((p) => {
      if (p.ref !== item.ref) return p;
      const legs = { ...p.legs };
      delete legs[item.terminal];
      return { ...p, legs };
    }),
  };
}

export const replaceWire = (bb: Breadboard, w: Jumper): Breadboard => ({
  ...bb,
  wires: bb.wires.map((x) => (x.id === w.id ? w : x)),
});
