/** Grid geometry shared with the backend (circuitos/schematic/library.py and netlist.py). */
import type { Component, PinDef, Point, Schematic, SymbolDef } from "./types";

/** Pixels per grid unit on screen at zoom 1. */
export const GRID = 20;

/** Mirror (x → −x), then rotate clockwise on screen (y downwards). */
export function transform(dx: number, dy: number, rot: number, mirror: boolean): Point {
  let x = mirror ? -dx : dx;
  let y = dy;
  for (let k = 0; k < (((rot / 90) % 4) + 4) % 4; k++) [x, y] = [-y, x];
  return [x + 0, y + 0]; // + 0 turns −0 into 0
}

export function subcktPins(c: Component): string[] {
  const names = (c.params.pins ?? "1 2").replace(/,/g, " ").split(/\s+/).filter(Boolean);
  return names.length ? names : ["1"];
}

export function pinDefs(c: Component, sym: SymbolDef | undefined): PinDef[] {
  if (c.kind !== "subckt") return sym?.pins ?? [];
  const names = subcktPins(c);
  const left = Math.ceil(names.length / 2);
  return [
    ...names.slice(0, left).map((name, i) => ({ name, dx: -3, dy: 2 * i })),
    ...names.slice(left).map((name, i) => ({ name, dx: 3, dy: 2 * i })),
  ];
}

export function pinPositions(c: Component, sym: SymbolDef | undefined): Record<string, Point> {
  const out: Record<string, Point> = {};
  for (const p of pinDefs(c, sym)) {
    const [dx, dy] = transform(p.dx, p.dy, c.rot, c.mirror);
    out[p.name] = [c.x + dx, c.y + dy];
  }
  return out;
}

export const key = (p: Point) => `${p[0]},${p[1]}`;

export function onSegment(p: Point, a: Point, b: Point): boolean {
  const [px, py] = p;
  const [ax, ay] = a;
  const [bx, by] = b;
  if ((bx - ax) * (py - ay) !== (by - ay) * (px - ax)) return false;
  return (
    Math.min(ax, bx) <= px &&
    px <= Math.max(ax, bx) &&
    Math.min(ay, by) <= py &&
    py <= Math.max(ay, by)
  );
}

/** Orthogonal route from a to b: horizontal first (or vertical first). */
export function route(a: Point, b: Point, verticalFirst = false): Point[] {
  if (a[0] === b[0] || a[1] === b[1]) return [a, b];
  const corner: Point = verticalFirst ? [a[0], b[1]] : [b[0], a[1]];
  return [a, corner, b];
}

/** Remove repeated and collinear middle points. */
export function simplify(points: Point[]): Point[] {
  const out: Point[] = [];
  for (const p of points) {
    const last = out[out.length - 1];
    if (last && last[0] === p[0] && last[1] === p[1]) continue;
    out.push(p);
    while (out.length >= 3) {
      const [a, b, c] = out.slice(-3) as [Point, Point, Point];
      if ((b[0] - a[0]) * (c[1] - a[1]) === (b[1] - a[1]) * (c[0] - a[0])) out.splice(-2, 1);
      else break;
    }
  }
  return out;
}

/**
 * Junction dots: points where three or more connections meet (pins, wire ends, T joints),
 * as the backend's connectivity rules.
 */
export function junctions(sch: Schematic, lib: Record<string, SymbolDef>): Point[] {
  const count = new Map<string, number>();
  const bump = (p: Point, n = 1) => count.set(key(p), (count.get(key(p)) ?? 0) + n);
  const anchors: Point[] = [];
  for (const c of sch.components) {
    for (const p of Object.values(pinPositions(c, lib[c.kind]))) {
      bump(p);
      anchors.push(p);
    }
  }
  for (const w of sch.wires) {
    const ends = [w.points[0]!, w.points[w.points.length - 1]!];
    for (const p of ends) bump(p);
    for (const p of w.points.slice(1, -1)) bump(p, 2);
    anchors.push(...w.points);
  }
  for (const w of sch.wires) {
    for (let i = 0; i + 1 < w.points.length; i++) {
      const a = w.points[i]!;
      const b = w.points[i + 1]!;
      const seen = new Set<string>();
      for (const p of anchors) {
        const k = key(p);
        if (seen.has(k) || k === key(a) || k === key(b)) continue;
        if (onSegment(p, a, b)) {
          seen.add(k);
          bump(p, 2);
        }
      }
    }
  }
  return [...count.entries()]
    .filter(([, n]) => n >= 3)
    .map(([k]) => k.split(",").map(Number) as Point);
}

/** Distance (grid units) from p to segment ab. */
export function segmentDistance(p: [number, number], a: Point, b: Point): number {
  const [px, py] = p;
  const [ax, ay] = a;
  const [bx, by] = b;
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/** Next free designator for a prefix: R1, R2… */
export function nextRef(sch: Schematic, prefix: string): string {
  const used = new Set(sch.components.map((c) => c.ref.toUpperCase()));
  for (let k = 1; ; k++) {
    const ref = `${prefix}${k}`;
    if (!used.has(ref.toUpperCase())) return ref;
  }
}
