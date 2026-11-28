/** Editing operations on the schematic: group moves, copy/paste and automatic wiring. */
import { isSupplyPin, key, nextRef, onSegment, pinPositions, simplify } from "./geometry";
import type { Component, NetLabel, Point, Schematic, SymbolDef, Wire } from "./types";

export interface Group {
  components: string[];
  wires: string[];
  labels: string[];
}

export interface Clip {
  components: Component[];
  wires: Wire[];
  labels: NetLabel[];
}

const uid = (p: string) => `${p}${Math.random().toString(36).slice(2, 9)}`;

/** Rectangle of a component body: its pins and centre, half a grid unit around. */
export function bodyRect(
  c: Component,
  sym: SymbolDef | undefined,
): [number, number, number, number] {
  const pts = Object.values(pinPositions(c, sym));
  const xs = [c.x - 0.5, c.x + 0.5, ...pts.map((p) => p[0])];
  const ys = [c.y - 0.5, c.y + 0.5, ...pts.map((p) => p[1])];
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/** Components, wires and labels inside the rectangle (corners in grid units, any order). */
export function itemsInBox(
  sch: Schematic,
  lib: Record<string, SymbolDef>,
  a: [number, number],
  b: [number, number],
): Group {
  const [x0, x1] = [Math.min(a[0], b[0]), Math.max(a[0], b[0])];
  const [y0, y1] = [Math.min(a[1], b[1]), Math.max(a[1], b[1])];
  const inside = (p: Point | [number, number]) =>
    p[0] >= x0 && p[0] <= x1 && p[1] >= y0 && p[1] <= y1;
  return {
    components: sch.components
      .filter((c) => {
        const [rx0, ry0, rx1, ry1] = bodyRect(c, lib[c.kind]);
        return inside([rx0, ry0]) && inside([rx1, ry1]);
      })
      .map((c) => c.id),
    wires: sch.wires.filter((w) => w.points.every(inside)).map((w) => w.id),
    labels: sch.labels.filter((l) => inside([l.x, l.y])).map((l) => l.id),
  };
}

/**
 * Move components, whole wires and labels by (dx, dy). Wire ends sitting on a moved pin follow
 * it (rubber band), keeping their segments orthogonal.
 */
export function moveItems(
  base: Schematic,
  lib: Record<string, SymbolDef>,
  group: Group,
  dx: number,
  dy: number,
): Schematic {
  if (!dx && !dy) return base;
  const ids = new Set(group.components);
  const wireIds = new Set(group.wires);
  const labelIds = new Set(group.labels);
  const moved = new Set<string>();
  for (const c of base.components)
    if (ids.has(c.id))
      for (const p of Object.values(pinPositions(c, lib[c.kind]))) moved.add(key(p));
  const wires = base.wires.map((w) => {
    if (wireIds.has(w.id))
      return { ...w, points: w.points.map((p) => [p[0] + dx, p[1] + dy] as Point) };
    const pts = w.points.map((p) => [...p] as Point);
    let changed = false;
    for (const i of [0, pts.length - 1]) {
      const pi0 = pts[i]!;
      if (!moved.has(key(pi0))) continue;
      const j = i === 0 ? 1 : pts.length - 2;
      const pj = pts[j]!;
      const horizontal = pj[1] === pi0[1];
      const pi: Point = [pi0[0] + dx, pi0[1] + dy];
      pts[i] = pi;
      if (pts.length > 2) {
        if (horizontal) pts[j] = [pj[0], pi[1]];
        else pts[j] = [pi[0], pj[1]];
      } else if (pi[0] !== pj[0] && pi[1] !== pj[1]) {
        const corner: Point = horizontal ? [pi[0], pj[1]] : [pj[0], pi[1]];
        pts.splice(i === 0 ? 1 : pts.length - 1, 0, corner);
      }
      changed = true;
    }
    return changed ? { ...w, points: simplify(pts) } : w;
  });
  return {
    ...base,
    wires,
    components: base.components.map((c) =>
      ids.has(c.id) ? { ...c, x: c.x + dx, y: c.y + dy } : c,
    ),
    labels: base.labels.map((l) => (labelIds.has(l.id) ? { ...l, x: l.x + dx, y: l.y + dy } : l)),
  };
}

/** Copy of the group (bench-instrument links are dropped: a copy is a plain part). */
export function copyItems(sch: Schematic, group: Group): Clip {
  const strip = (c: Component): Component => {
    const params = { ...c.params };
    for (const k of Object.keys(params)) if (k.startsWith("bench_")) delete params[k];
    return { ...c, params };
  };
  return {
    components: sch.components.filter((c) => group.components.includes(c.id)).map(strip),
    wires: sch.wires.filter((w) => group.wires.includes(w.id)),
    labels: sch.labels.filter((l) => group.labels.includes(l.id)),
  };
}

function refPrefix(ref: string): string {
  return ref.replace(/\d+$/, "") || "X";
}

/**
 * Paste a clip with its top-left corner at `at`. Components get new ids and free designators
 * (R1 → next free R); returns the new document and the pasted group.
 */
export function pasteClip(sch: Schematic, clip: Clip, at: Point): { sch: Schematic; group: Group } {
  const xs = [
    ...clip.components.map((c) => c.x),
    ...clip.wires.flatMap((w) => w.points.map((p) => p[0])),
    ...clip.labels.map((l) => l.x),
  ];
  const ys = [
    ...clip.components.map((c) => c.y),
    ...clip.wires.flatMap((w) => w.points.map((p) => p[1])),
    ...clip.labels.map((l) => l.y),
  ];
  if (!xs.length) return { sch, group: { components: [], wires: [], labels: [] } };
  const dx = at[0] - Math.min(...xs);
  const dy = at[1] - Math.min(...ys);
  let doc = sch;
  const comps: Component[] = [];
  for (const c of clip.components) {
    const ref = c.kind === "ground" ? nextRef(doc, "GND") : nextRef(doc, refPrefix(c.ref));
    const copy = { ...c, id: uid("c"), ref, x: c.x + dx, y: c.y + dy, params: { ...c.params } };
    comps.push(copy);
    doc = { ...doc, components: [...doc.components, copy] };
  }
  const wires = clip.wires.map((w) => ({
    id: uid("w"),
    points: w.points.map((p) => [p[0] + dx, p[1] + dy] as Point),
  }));
  const labels = clip.labels.map((l) => ({ ...l, id: uid("l"), x: l.x + dx, y: l.y + dy }));
  return {
    sch: { ...doc, wires: [...sch.wires, ...wires], labels: [...sch.labels, ...labels] },
    group: {
      components: comps.map((c) => c.id),
      wires: wires.map((w) => w.id),
      labels: labels.map((l) => l.id),
    },
  };
}

/** Pins with nothing attached (no other pin, label or wire on them). */
export function openPins(
  sch: Schematic,
  lib: Record<string, SymbolDef>,
): { comp: Component; pin: string; at: Point }[] {
  const pins: { comp: Component; pin: string; at: Point }[] = [];
  for (const c of sch.components)
    for (const [pin, at] of Object.entries(pinPositions(c, lib[c.kind])))
      pins.push({ comp: c, pin, at });
  const count = new Map<string, number>();
  for (const q of pins) count.set(key(q.at), (count.get(key(q.at)) ?? 0) + 1);
  return pins.filter(
    (q) =>
      (count.get(key(q.at)) ?? 0) < 2 &&
      !sch.labels.some((l) => l.x === q.at[0] && l.y === q.at[1]) &&
      !sch.wires.some((w) =>
        w.points.some((b, i) =>
          i === 0 || isSupplyPin(q.comp.kind, q.pin)
            ? key(b) === key(q.at)
            : onSegment(q.at, w.points[i - 1]!, b),
        ),
      ),
  );
}

/**
 * Straight wires between open pins of different components that face each other on the same
 * row or column, nearest pairs first. A wire is drawn only when its path is clear: it does not
 * cross a component body, does not touch another pin, label or wire (which would join nets
 * by accident) and is at most `maxLength` grid units long. Each pin takes one wire.
 */
export function autoWire(sch: Schematic, lib: Record<string, SymbolDef>, maxLength = 40): Wire[] {
  const open = openPins(sch, lib);
  const rects = sch.components.map((c) => bodyRect(c, lib[c.kind]));
  const anchors = new Set<string>();
  for (const c of sch.components)
    for (const p of Object.values(pinPositions(c, lib[c.kind]))) anchors.add(key(p));
  for (const l of sch.labels) anchors.add(`${l.x},${l.y}`);
  const onWire = (p: Point, wires: Wire[]) =>
    wires.some((w) => w.points.some((b, i) => i > 0 && onSegment(p, w.points[i - 1]!, b)));

  // targets: open pins of other components, then points of existing wires on the same line
  type Cand = { a: number; b: number | null; to: Point; len: number };
  const cands: Cand[] = [];
  for (let i = 0; i < open.length; i++) {
    const p = open[i]!;
    for (let j = i + 1; j < open.length; j++) {
      const q = open[j]!;
      if (p.comp.id === q.comp.id) continue;
      if (p.at[0] !== q.at[0] && p.at[1] !== q.at[1]) continue;
      const len = Math.abs(p.at[0] - q.at[0]) + Math.abs(p.at[1] - q.at[1]);
      if (len === 0 || len > maxLength) continue;
      cands.push({ a: i, b: j, to: q.at, len });
    }
    for (const w of sch.wires)
      for (let k = 1; k < w.points.length; k++) {
        const [a, b] = [w.points[k - 1]!, w.points[k]!];
        let hit: Point | null = null;
        if (a[0] === b[0] && Math.min(a[1], b[1]) <= p.at[1] && p.at[1] <= Math.max(a[1], b[1]))
          hit = [a[0], p.at[1]];
        else if (
          a[1] === b[1] &&
          Math.min(a[0], b[0]) <= p.at[0] &&
          p.at[0] <= Math.max(a[0], b[0])
        )
          hit = [p.at[0], a[1]];
        if (!hit) continue;
        const len = Math.abs(p.at[0] - hit[0]) + Math.abs(p.at[1] - hit[1]);
        if (len === 0 || len > maxLength) continue;
        // pin-to-pin first at equal length
        cands.push({ a: i, b: null, to: hit, len: len + 0.5 });
      }
  }
  cands.sort((x, y) => x.len - y.len);
  const used = new Set<number>();
  const added: Wire[] = [];
  const blocked = (pt: Point, end: Point) =>
    (key(pt) !== key(end) && anchors.has(key(pt))) ||
    (key(pt) !== key(end) && onWire(pt, sch.wires)) ||
    onWire(pt, added);
  for (const { a, b, to } of cands) {
    if (used.has(a) || (b !== null && used.has(b))) continue;
    const p = open[a]!.at;
    const q = to;
    const sx = Math.sign(q[0] - p[0]);
    const sy = Math.sign(q[1] - p[1]);
    let clear = true;
    for (let x = p[0] + sx, y = p[1] + sy; ; x += sx, y += sy) {
      const pt: Point = [x, y];
      const last = x === q[0] && y === q[1];
      if (!last && blocked(pt, q)) clear = false;
      else if (!last && rects.some(([x0, y0, x1, y1]) => x > x0 && x < x1 && y > y0 && y < y1))
        clear = false;
      // half step: a body thinner than one grid unit between two grid points
      const hx = x - sx / 2;
      const hy = y - sy / 2;
      if (rects.some(([x0, y0, x1, y1]) => hx > x0 && hx < x1 && hy > y0 && hy < y1)) clear = false;
      if (!clear || last) break;
    }
    // a wire ending on another wire must not land on one just added (would merge nets)
    if (!clear || onWire(p, added) || onWire(q, added)) continue;
    used.add(a);
    if (b !== null) used.add(b);
    added.push({ id: uid("w"), points: [p, q] });
  }
  return added;
}
