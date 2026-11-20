/** SVG schematic editor: grid, placement, drag, rotation, orthogonal wires, labels and probes. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  GRID,
  junctions,
  key,
  nextRef,
  onSegment,
  pinPositions,
  route,
  segmentDistance,
  simplify,
} from "./geometry";
import { SymbolBody, valueText, type Glow } from "./symbols";
import { copyItems, itemsInBox, moveItems, pasteClip, type Clip, type Group } from "./editing";
import { removeSources } from "../breadboard/instruments";
import { MOTOR_KINDS, rotationText } from "../breadboard/DeviceFaces";
import type { Motion } from "../breadboard/DeviceFaces";
import type { Component, Point, Probe, ProbeKind, Schematic, SymbolDef } from "./types";

export type Tool =
  | { kind: "select" }
  | {
      kind: "place";
      symbol: string;
      /** preset parameters and catalogue part (LEDs and lamps of the palette) */
      params?: Record<string, string>;
      part_id?: string | null;
    }
  | { kind: "wire" }
  | { kind: "label" }
  | { kind: "probe"; probe: ProbeKind };

export type Selection =
  | { kind: "component"; id: string }
  | { kind: "wire"; id: string }
  | { kind: "label"; id: string }
  | ({ kind: "group" } & Group)
  | null;

/** Clipboard shared by every editor of the page (copy in one circuit, paste in another). */
let clipboard: Clip | null = null;

interface Props {
  nodeNames?: Record<string, string[]>;
  schematic: Schematic;
  library: Record<string, SymbolDef>;
  tool: Tool;
  setTool: (t: Tool) => void;
  selection: Selection;
  setSelection: (s: Selection) => void;
  onChange: (s: Schematic) => void;
  probeColors: Record<string, string>;
  /** Shaft speed of each motor after the last simulation (direction of rotation). */
  motion?: Record<string, Motion>;
  /** Brightness of each LED and lamp after the last simulation. */
  glows?: Record<string, Glow>;
  /** Short message for the status line (e.g. result of a paste). */
  onNotice?: (text: string) => void;
}

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_PRESETS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4];

const uid = (p: string) => `${p}${Math.random().toString(36).slice(2, 9)}`;

export function SchematicEditor({
  nodeNames = {},
  schematic: sch,
  library,
  tool,
  setTool,
  selection,
  setSelection,
  onChange,
  probeColors,
  motion,
  glows,
  onNotice,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState({ x: -12, y: -10, scale: 1 });
  const [cursor, setCursor] = useState<Point>([0, 0]);
  const cursorRef = useRef<Point>([0, 0]);
  const placing = tool.kind === "place" ? tool.symbol : "";
  useEffect(() => {
    setPlaceRot(0);
    setPlaceMirror(false);
  }, [placing]);
  const [wire, setWire] = useState<Point[] | null>(null);
  const [verticalFirst, setVerticalFirst] = useState(false);
  const [diffStart, setDiffStart] = useState<Point | null>(null);
  // orientation of the part about to be placed (R and M work before the click)
  const [placeRot, setPlaceRot] = useState<Component["rot"]>(0);
  const [placeMirror, setPlaceMirror] = useState(false);
  const [box, setBox] = useState<{ a: [number, number]; b: [number, number] } | null>(null);
  const fitRef = useRef<() => void>(() => {});
  const drag = useRef<{
    kind: "component" | "pan" | "box";
    group?: Group;
    id?: string;
    start: Point;
    origin: Point;
    snapshot: Schematic;
    moved: boolean;
    client: [number, number];
  } | null>(null);

  // ------------------------------------------------------------------ coordinates
  const toGrid = useCallback(
    (clientX: number, clientY: number): [number, number] => {
      const svg = svgRef.current;
      if (!svg) return [0, 0];
      const r = svg.getBoundingClientRect();
      return [
        view.x + (clientX - r.left) / (GRID * view.scale),
        view.y + (clientY - r.top) / (GRID * view.scale),
      ];
    },
    [view],
  );
  const snap = (p: [number, number]): Point => [Math.round(p[0]), Math.round(p[1])];

  const pins = useMemo(() => {
    const out: { comp: Component; pin: string; at: Point }[] = [];
    for (const c of sch.components)
      for (const [pin, at] of Object.entries(pinPositions(c, library[c.kind])))
        out.push({ comp: c, pin, at });
    return out;
  }, [sch.components, library]);

  const dots = useMemo(() => junctions(sch, library), [sch, library]);
  // pins with nothing attached get an open-circle marker (as in usual schematic editors)
  const openPins = useMemo(() => {
    const count = new Map<string, number>();
    for (const q of pins) count.set(key(q.at), (count.get(key(q.at)) ?? 0) + 1);
    return pins.filter(
      (q) =>
        (count.get(key(q.at)) ?? 0) < 2 &&
        !sch.labels.some((l) => l.x === q.at[0] && l.y === q.at[1]) &&
        !sch.wires.some((w) =>
          w.points.some((b, i) =>
            i === 0 ? key(b) === key(q.at) : onSegment(q.at, w.points[i - 1]!, b),
          ),
        ),
    );
  }, [pins, sch.labels, sch.wires]);

  // ------------------------------------------------------------------ hit tests
  const hitComponent = (p: [number, number]): Component | undefined => {
    for (const c of [...sch.components].reverse()) {
      const pp = Object.values(pinPositions(c, library[c.kind]));
      const xs = [c.x, ...pp.map((q) => q[0])];
      const ys = [c.y, ...pp.map((q) => q[1])];
      const pad = 0.6;
      if (
        p[0] >= Math.min(...xs) - pad &&
        p[0] <= Math.max(...xs) + pad &&
        p[1] >= Math.min(...ys) - pad &&
        p[1] <= Math.max(...ys) + pad
      )
        return c;
    }
    return undefined;
  };
  const hitWire = (p: [number, number]) =>
    sch.wires.find((w) =>
      w.points.slice(1).some((b, i) => segmentDistance(p, w.points[i]!, b) < 0.35),
    );
  const hitLabel = (p: [number, number]) =>
    sch.labels.find((l) => Math.abs(l.x - p[0]) < 0.8 && Math.abs(l.y - p[1]) < 0.8);
  const nearestPin = (c: Component, p: [number, number]) => {
    let best = "";
    let dist = Infinity;
    for (const [name, at] of Object.entries(pinPositions(c, library[c.kind]))) {
      const d = Math.hypot(at[0] - p[0], at[1] - p[1]);
      if (d < dist) [best, dist] = [name, d];
    }
    return best;
  };
  const isConnectionPoint = (p: Point) =>
    pins.some((q) => key(q.at) === key(p)) ||
    sch.labels.some((l) => l.x === p[0] && l.y === p[1]) ||
    sch.wires.some((w) => w.points.some((q, i) => i > 0 && onSegment(p, w.points[i - 1]!, q)));

  // ------------------------------------------------------------------ actions
  const addProbe = (probe: Omit<Probe, "id">) =>
    onChange({ ...sch, probes: [...sch.probes, { id: uid("p"), ...probe }] });

  const finishWire = (points: Point[]) => {
    const pts = simplify(points);
    if (pts.length >= 2) onChange({ ...sch, wires: [...sch.wires, { id: uid("w"), points: pts }] });
    setWire(null);
  };

  const place = (t: Extract<Tool, { kind: "place" }>, at: Point) => {
    const symbol = t.symbol;
    const sym = library[symbol];
    if (!sym) return;
    const comp: Component = {
      id: uid("c"),
      kind: symbol,
      ref: nextRef(sch, symbol === "ground" ? "GND" : sym.prefix),
      x: at[0],
      y: at[1],
      rot: placeRot,
      mirror: placeMirror,
      params: { ...(t.params ?? {}) },
      part_id: t.part_id ?? null,
    };
    onChange({ ...sch, components: [...sch.components, comp] });
    setSelection({ kind: "component", id: comp.id });
  };

  const moveComponent = (base: Schematic, id: string, to: Point): Schematic => {
    const comp = base.components.find((c) => c.id === id);
    if (!comp) return base;
    return moveItems(
      base,
      library,
      { components: [id], wires: [], labels: [] },
      to[0] - comp.x,
      to[1] - comp.y,
    );
  };

  const groupOf = (s: Selection): Group | null =>
    s?.kind === "group"
      ? { components: s.components, wires: s.wires, labels: s.labels }
      : s?.kind === "component"
        ? { components: [s.id], wires: [], labels: [] }
        : s?.kind === "wire"
          ? { components: [], wires: [s.id], labels: [] }
          : s?.kind === "label"
            ? { components: [], wires: [], labels: [s.id] }
            : null;

  const copySelected = useCallback(() => {
    const g = groupOf(selection);
    if (!g) return false;
    clipboard = copyItems(sch, g);
    const n = clipboard.components.length;
    onNotice?.(n ? `${n} componente(s) copiado(s): Ctrl+V cola no cursor` : "Nada para copiar");
    return true;
  }, [selection, sch, onNotice]);

  const pasteAt = useCallback(
    (at: Point) => {
      if (!clipboard) return;
      const out = pasteClip(sch, clipboard, at);
      onChange(out.sch);
      const g = out.group;
      setSelection(
        g.components.length === 1 && !g.wires.length && !g.labels.length
          ? { kind: "component", id: g.components[0]! }
          : { kind: "group", ...g },
      );
      setTool({ kind: "select" });
    },
    [sch, onChange, setSelection, setTool],
  );

  const duplicateSelected = useCallback(() => {
    const g = groupOf(selection);
    if (!g) return;
    clipboard = copyItems(sch, g);
    const xs = clipboard.components.map((c) => c.x);
    const ys = clipboard.components.map((c) => c.y);
    if (!xs.length) return;
    pasteAt([Math.min(...xs) + 3, Math.min(...ys) + 3]);
  }, [selection, sch, pasteAt]);

  const rotateSelected = useCallback(() => {
    if (tool.kind === "place") {
      setPlaceRot((r) => ((r + 90) % 360) as Component["rot"]);
      return;
    }
    if (selection?.kind !== "component") return;
    onChange({
      ...sch,
      components: sch.components.map((c) =>
        c.id === selection.id ? { ...c, rot: ((c.rot + 90) % 360) as Component["rot"] } : c,
      ),
    });
  }, [selection, sch, onChange, tool.kind]);

  const mirrorSelected = useCallback(() => {
    if (tool.kind === "place") {
      setPlaceMirror((m) => !m);
      return;
    }
    if (selection?.kind !== "component") return;
    onChange({
      ...sch,
      components: sch.components.map((c) =>
        c.id === selection.id ? { ...c, mirror: !c.mirror } : c,
      ),
    });
  }, [selection, sch, onChange, tool.kind]);

  const deleteSelected = useCallback(() => {
    if (!selection) return;
    if (selection.kind === "group") {
      const doc = removeSources(sch, selection.components);
      onChange({
        ...doc,
        wires: doc.wires.filter((w) => !selection.wires.includes(w.id)),
        labels: doc.labels.filter((l) => !selection.labels.includes(l.id)),
      });
    } else if (selection.kind === "component") {
      onChange(removeSources(sch, [selection.id]));
    } else if (selection.kind === "wire") {
      onChange({ ...sch, wires: sch.wires.filter((w) => w.id !== selection.id) });
    } else {
      onChange({ ...sch, labels: sch.labels.filter((l) => l.id !== selection.id) });
    }
    setSelection(null);
  }, [selection, sch, onChange, setSelection]);

  /** Zoom to `target` (or by `factor`) keeping the grid point under (clientX, clientY). */
  const zoomAt = useCallback(
    (next: (scale: number) => number, clientX?: number, clientY?: number) => {
      const svg = svgRef.current;
      if (!svg) return;
      const r = svg.getBoundingClientRect();
      const cx = clientX ?? r.left + r.width / 2;
      const cy = clientY ?? r.top + r.height / 2;
      setView((v) => {
        const gx = v.x + (cx - r.left) / (GRID * v.scale);
        const gy = v.y + (cy - r.top) / (GRID * v.scale);
        const scale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next(v.scale)));
        const k = v.scale / scale;
        return { scale, x: gx - (gx - v.x) * k, y: gy - (gy - v.y) * k };
      });
    },
    [],
  );
  const zoomIn = useCallback(() => zoomAt((s) => s * 1.25), [zoomAt]);
  const zoomOut = useCallback(() => zoomAt((s) => s / 1.25), [zoomAt]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (e.ctrlKey || e.metaKey) {
        const k = e.key.toLowerCase();
        if (k === "c") {
          if (copySelected()) e.preventDefault();
        } else if (k === "v" && clipboard) {
          e.preventDefault();
          pasteAt(cursorRef.current);
        } else if (k === "d") {
          e.preventDefault();
          duplicateSelected();
        } else if (k === "a") {
          e.preventDefault();
          setSelection({
            kind: "group",
            components: sch.components.map((c) => c.id),
            wires: sch.wires.map((w) => w.id),
            labels: sch.labels.map((l) => l.id),
          });
        }
        return;
      }
      if (e.key === "Escape") {
        setWire(null);
        setDiffStart(null);
        setTool({ kind: "select" });
      } else if (e.key === "r" || e.key === "R") rotateSelected();
      else if (e.key === "m" || e.key === "M") mirrorSelected();
      else if (e.key === "Delete" || e.key === "Backspace") deleteSelected();
      else if (e.key === "w" || e.key === "W") setTool({ kind: "wire" });
      else if (e.key === "+" || e.key === "=") zoomIn();
      else if (e.key === "-" || e.key === "_") zoomOut();
      else if (e.key === "0") zoomAt(() => 1);
      else if (e.key === "f" || e.key === "F") fitRef.current();
      else if (e.key === " " && wire) {
        e.preventDefault();
        setVerticalFirst((v) => !v);
      } else return;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    rotateSelected,
    mirrorSelected,
    deleteSelected,
    setTool,
    wire,
    zoomIn,
    zoomOut,
    zoomAt,
    copySelected,
    pasteAt,
    duplicateSelected,
    setSelection,
    sch,
  ]);

  // ------------------------------------------------------------------ pointer
  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    const raw = toGrid(e.clientX, e.clientY);
    const p = snap(raw);
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      drag.current = {
        kind: "pan",
        start: [view.x, view.y],
        origin: p,
        snapshot: sch,
        moved: false,
        client: [e.clientX, e.clientY],
      };
      (e.target as Element).setPointerCapture?.(e.pointerId);
      return;
    }
    if (e.button !== 0) return;
    if (tool.kind === "place") {
      place(tool, p);
      if (!e.shiftKey) setTool({ kind: "select" });
      return;
    }
    if (tool.kind === "wire") {
      if (!wire) setWire([p]);
      else {
        const pts = [...wire.slice(0, -1), ...route(wire[wire.length - 1]!, p, verticalFirst)];
        if (e.detail >= 2 || isConnectionPoint(p)) finishWire(pts);
        else setWire([...pts.slice(0, -1), p]);
      }
      return;
    }
    if (tool.kind === "label") {
      const id = uid("l");
      onChange({ ...sch, labels: [...sch.labels, { id, name: "out", x: p[0], y: p[1] }] });
      setSelection({ kind: "label", id });
      setTool({ kind: "select" });
      return;
    }
    if (tool.kind === "probe") {
      const pk = tool.probe;
      if (pk === "i" || pk === "p") {
        const c = hitComponent(raw);
        if (c && c.kind !== "ground")
          addProbe({ kind: pk, component: c.ref, pin: pk === "i" ? nearestPin(c, raw) : null });
        return;
      }
      if (!isConnectionPoint(p)) return;
      if (pk === "v") addProbe({ kind: "v", target: { at: p } });
      else if (!diffStart) setDiffStart(p);
      else {
        addProbe({ kind: "vdiff", target: { at: diffStart }, reference: { at: p } });
        setDiffStart(null);
      }
      return;
    }
    // select
    const lb = hitLabel(raw);
    if (lb) {
      setSelection({ kind: "label", id: lb.id });
      return;
    }
    const c = hitComponent(raw);
    if (c) {
      const inGroup = selection?.kind === "group" && selection.components.includes(c.id);
      if (!inGroup) setSelection({ kind: "component", id: c.id });
      drag.current = {
        kind: "component",
        id: c.id,
        group:
          inGroup && selection?.kind === "group"
            ? { components: selection.components, wires: selection.wires, labels: selection.labels }
            : undefined,
        start: [c.x, c.y],
        origin: p,
        snapshot: sch,
        moved: false,
        client: [e.clientX, e.clientY],
      };
      (e.target as Element).setPointerCapture?.(e.pointerId);
      return;
    }
    const w = hitWire(raw);
    if (w) {
      setSelection({ kind: "wire", id: w.id });
      return;
    }
    // empty background: drag a rectangle to select several items (pan: middle button, Alt)
    setSelection(null);
    drag.current = {
      kind: "box",
      start: raw,
      origin: p,
      snapshot: sch,
      moved: false,
      client: [e.clientX, e.clientY],
    };
    setBox({ a: raw, b: raw });
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const raw = toGrid(e.clientX, e.clientY);
    setCursor(snap(raw));
    cursorRef.current = snap(raw);
    const d = drag.current;
    if (!d) return;
    if (d.kind === "box") {
      d.moved = true;
      setBox({ a: d.start, b: raw });
      return;
    }
    if (d.kind === "pan") {
      const dx = (e.clientX - d.client[0]) / (GRID * view.scale);
      const dy = (e.clientY - d.client[1]) / (GRID * view.scale);
      setView((v) => ({ ...v, x: d.start[0] - dx, y: d.start[1] - dy }));
      return;
    }
    const p = snap(raw);
    const to: Point = [d.start[0] + p[0] - d.origin[0], d.start[1] + p[1] - d.origin[1]];
    if (to[0] !== d.start[0] || to[1] !== d.start[1] || d.moved) {
      d.moved = true;
      onChange(
        d.group
          ? moveItems(d.snapshot, library, d.group, to[0] - d.start[0], to[1] - d.start[1])
          : moveComponent(d.snapshot, d.id!, to),
      );
    }
  };

  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    if (d?.kind === "box") {
      setBox(null);
      if (!box || Math.hypot(box.b[0] - box.a[0], box.b[1] - box.a[1]) < 0.5) return;
      const g = itemsInBox(sch, library, box.a, box.b);
      const n = g.components.length + g.wires.length + g.labels.length;
      if (!n) return;
      if (g.components.length === 1 && n === 1)
        setSelection({ kind: "component", id: g.components[0]! });
      else setSelection({ kind: "group", ...g });
    }
  };

  const onWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    zoomAt((s) => s * factor, e.clientX, e.clientY);
  };

  const fit = () => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const c of sch.components) {
      xs.push(c.x - 3, c.x + 3);
      ys.push(c.y - 3, c.y + 3);
    }
    for (const w of sch.wires)
      for (const p of w.points) {
        xs.push(p[0]);
        ys.push(p[1]);
      }
    for (const l of sch.labels) {
      xs.push(l.x - 2, l.x + 2);
      ys.push(l.y - 1, l.y + 1);
    }
    const svg = svgRef.current;
    if (!xs.length || !svg) return;
    const r = svg.getBoundingClientRect();
    const w = Math.max(...xs) - Math.min(...xs) + 4;
    const h = Math.max(...ys) - Math.min(...ys) + 4;
    const scale = Math.min(
      2,
      Math.max(0.25, Math.min(r.width / (w * GRID), r.height / (h * GRID))),
    );
    setView({
      scale,
      x: (Math.min(...xs) + Math.max(...xs)) / 2 - r.width / (2 * GRID * scale),
      y: (Math.min(...ys) + Math.max(...ys)) / 2 - r.height / (2 * GRID * scale),
    });
  };

  // Keep the drawing visible when opening the library or changing the viewport width.
  // Observe size changes only: editing, panning and zooming must not trigger an auto-fit.
  useEffect(() => {
    fitRef.current = fit;
  });
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    let { width, height } = svg.getBoundingClientRect();
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const next = entry.contentRect;
      if (Math.abs(next.width - width) < 1 && Math.abs(next.height - height) < 1) return;
      width = next.width;
      height = next.height;
      fitRef.current();
    });
    observer.observe(svg);
    return () => observer.disconnect();
  }, []);

  // auto-fit when a new document is loaded (component ids change completely)
  const docKey = sch.components.map((c) => c.id).join("|");
  const lastDoc = useRef("");
  useEffect(() => {
    const prev = lastDoc.current.split("|");
    const now = docKey.split("|");
    if (now.length > 1 && !now.some((id) => prev.includes(id))) fit();
    lastDoc.current = docKey;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docKey]);

  // ------------------------------------------------------------------ render
  const pinNode = (p: Point) => <circle key={key(p)} cx={p[0] * GRID} cy={p[1] * GRID} r={2.5} />;
  const preview =
    tool.kind === "wire" && wire
      ? [...wire.slice(0, -1), ...route(wire[wire.length - 1]!, cursor, verticalFirst)]
      : null;
  const ghost =
    tool.kind === "place" && library[tool.symbol]
      ? ({
          id: "ghost",
          kind: tool.symbol,
          ref: "",
          x: cursor[0],
          y: cursor[1],
          rot: placeRot,
          mirror: placeMirror,
          params: { ...(tool.params ?? {}) },
          part_id: tool.part_id ?? null,
        } as Component)
      : null;

  const probeMarks = sch.probes.flatMap((pr) => {
    const color = probeColors[pr.id] ?? "#888";
    const marks: React.ReactNode[] = [];
    const at = (p: Point | null | undefined, tag: string) =>
      p &&
      marks.push(
        <g key={`${pr.id}${tag}`} transform={`translate(${p[0] * GRID},${p[1] * GRID})`}>
          <path d="M0 0 L-6 -14 L6 -14 Z" fill={color} stroke="none" />
          <text y={-17} textAnchor="middle" fontSize={10} fill={color}>
            {tag}
          </text>
        </g>,
      );
    if (pr.kind === "v") at(pr.target?.at, "V");
    if (pr.kind === "vdiff") {
      at(pr.target?.at, "+");
      at(pr.reference?.at, "−");
    }
    if (pr.kind === "i" || pr.kind === "p") {
      const c = sch.components.find((x) => x.ref === pr.component);
      if (c) {
        const pp = pinPositions(c, library[c.kind]);
        const pin: Point = (pr.pin ? pp[pr.pin] : undefined) ?? [c.x, c.y];
        marks.push(
          <g key={pr.id} transform={`translate(${pin[0] * GRID},${pin[1] * GRID})`}>
            <circle r={7} fill="none" stroke={color} strokeWidth={2} />
            <text y={-11} textAnchor="middle" fontSize={10} fill={color}>
              {pr.kind === "i" ? "I" : "P"}
            </text>
          </g>,
        );
      }
    }
    return marks;
  });

  const cursorClass = tool.kind === "select" ? "" : tool.kind === "probe" ? " probing" : " drawing";

  return (
    <div className="schematic-editor">
      <div className="zoom-controls" role="group" aria-label="Zoom do esquemático">
        <button type="button" className="secondary" onClick={zoomOut} title="Diminuir zoom (−)">
          −
        </button>
        <select
          aria-label="Nível de zoom"
          value={String(view.scale)}
          onChange={(e) => {
            const z = Number(e.target.value);
            zoomAt(() => z);
          }}
        >
          {!ZOOM_PRESETS.includes(view.scale) && (
            <option value={String(view.scale)}>{Math.round(view.scale * 100)} %</option>
          )}
          {ZOOM_PRESETS.map((z) => (
            <option key={z} value={String(z)}>
              {z * 100} %
            </option>
          ))}
        </select>
        <button type="button" className="secondary" onClick={zoomIn} title="Aumentar zoom (+)">
          +
        </button>
        <button
          type="button"
          className="secondary"
          onClick={fit}
          title="Ajustar o desenho à tela (F)"
        >
          Ajustar
        </button>
      </div>
      <svg
        ref={svgRef}
        className={`schematic-canvas${cursorClass}`}
        role="application"
        aria-label="Área de desenho do esquemático"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onWheel={onWheel}
        onContextMenu={(e) => {
          e.preventDefault();
          if (wire && preview) finishWire(preview.slice(0, -1));
          else setTool({ kind: "select" });
        }}
      >
        <defs>
          <pattern
            id="grid"
            width={GRID * view.scale}
            height={GRID * view.scale}
            patternUnits="userSpaceOnUse"
            x={-view.x * GRID * view.scale}
            y={-view.y * GRID * view.scale}
          >
            <circle cx={1} cy={1} r={1} className="grid-dot" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
        <g transform={`scale(${view.scale}) translate(${-view.x * GRID},${-view.y * GRID})`}>
          {sch.wires.map((w) => (
            <polyline
              key={w.id}
              className={
                (selection?.kind === "wire" && selection.id === w.id) ||
                (selection?.kind === "group" && selection.wires.includes(w.id))
                  ? "wire sel"
                  : "wire"
              }
              points={w.points.map((p) => `${p[0] * GRID},${p[1] * GRID}`).join(" ")}
            />
          ))}
          {preview && (
            <polyline
              className="wire preview"
              points={preview.map((p) => `${p[0] * GRID},${p[1] * GRID}`).join(" ")}
            />
          )}
          {[...sch.components, ...(ghost ? [ghost] : [])].map((c) => {
            const sym = library[c.kind];
            const selected =
              (selection?.kind === "component" && selection.id === c.id) ||
              (selection?.kind === "group" && selection.components.includes(c.id));
            const pinXs = Object.values(pinPositions(c, sym)).map((q) => q[0]);
            const vertical = pinXs.length > 1 && pinXs.every((x) => x === pinXs[0]);
            const isGround = c.kind === "ground";
            return (
              <g
                key={c.id}
                className={`comp${selected ? " sel" : ""}${c.id === "ghost" ? " ghost" : ""}`}
              >
                <g
                  transform={`translate(${c.x * GRID},${c.y * GRID}) rotate(${c.rot}) scale(${c.mirror ? -1 : 1},1)`}
                >
                  <SymbolBody c={c} sym={sym} glow={glows?.[c.ref]} />
                </g>
                {!isGround && c.id !== "ghost" && (
                  <text
                    className="ref-text"
                    x={(c.x + (vertical ? 1.4 : 0)) * GRID}
                    y={(c.y + (vertical ? -0.3 : -1.5)) * GRID}
                    textAnchor={vertical ? "start" : "middle"}
                  >
                    <tspan className="ref">{c.ref}</tspan>
                    <tspan x={(c.x + (vertical ? 1.4 : 0)) * GRID} dy={13} className="val">
                      {valueText(c, sym)}
                    </tspan>
                  </text>
                )}
                {MOTOR_KINDS.has(c.kind) && motion?.[c.ref] && (
                  <text
                    className="sym-motion"
                    x={c.x * GRID}
                    y={(c.y + 3.6) * GRID}
                    textAnchor="middle"
                  >
                    {rotationText(motion[c.ref])}
                  </text>
                )}
              </g>
            );
          })}
          <g className="pins">{openPins.map((p) => pinNode(p.at))}</g>
          <g className="junctions">
            {dots.map((p) => (
              <circle key={key(p)} cx={p[0] * GRID} cy={p[1] * GRID} r={4} />
            ))}
          </g>
          {sch.labels.map((l) => (
            <g
              key={l.id}
              className={
                (selection?.kind === "label" && selection.id === l.id) ||
                (selection?.kind === "group" && selection.labels.includes(l.id))
                  ? "netlabel sel"
                  : "netlabel"
              }
              transform={`translate(${l.x * GRID},${l.y * GRID})`}
            >
              <line x1={0} y1={0} x2={0} y2={-8} />
              <path
                d={`M0 -8 L4 -22 L${12 + l.name.length * 7} -22 L${12 + l.name.length * 7} -8 Z`}
              />
              <text x={8} y={-11} fontSize={11}>
                {l.name}
              </text>
            </g>
          ))}
          <g className="node-annotations" pointerEvents="none">
            {Object.entries(nodeNames).map(([name, members]) => {
              const pin = pins.find((p) => members.includes(`${p.comp.ref}.${p.pin}`));
              if (!pin || sch.labels.some((l) => l.name.toLowerCase() === name.toLowerCase()))
                return null;
              return (
                <text key={name} x={pin.at[0] * GRID + 8} y={pin.at[1] * GRID - 9} fontSize={11}>
                  {name}
                </text>
              );
            })}
          </g>
          {probeMarks}
          {diffStart && (
            <circle
              cx={diffStart[0] * GRID}
              cy={diffStart[1] * GRID}
              r={6}
              className="diff-start"
            />
          )}
          {box && (
            <rect
              className="select-box"
              x={Math.min(box.a[0], box.b[0]) * GRID}
              y={Math.min(box.a[1], box.b[1]) * GRID}
              width={Math.abs(box.b[0] - box.a[0]) * GRID}
              height={Math.abs(box.b[1] - box.a[1]) * GRID}
            />
          )}
          {tool.kind !== "select" && (
            <circle cx={cursor[0] * GRID} cy={cursor[1] * GRID} r={3} className="cursor-dot" />
          )}
        </g>
      </svg>
      <div className="canvas-status small muted">
        <span>
          ({cursor[0]}, {cursor[1]}) · zoom {Math.round(view.scale * 100)} %
        </span>
        <span>
          {tool.kind === "wire"
            ? "Fio: clique nos vértices; termina num pino, fio ou duplo clique · espaço alterna o canto · Esc cancela"
            : tool.kind === "place"
              ? "Clique para posicionar · R gira e M espelha antes de inserir · Shift mantém a ferramenta · Esc cancela"
              : tool.kind === "probe"
                ? tool.probe === "vdiff"
                  ? diffStart
                    ? "Clique no nó de referência (−)"
                    : "Clique no nó positivo (+)"
                  : tool.probe === "v"
                    ? "Clique num fio ou pino"
                    : "Clique no componente (corrente entra pelo pino mais próximo)"
                : selection?.kind === "group"
                  ? `${selection.components.length} componente(s) selecionado(s): arraste para mover · Ctrl+C copia · Ctrl+D duplica · Del apaga`
                  : "Arraste para mover · arraste o fundo: selecionar vários · R gira · M espelha · Ctrl+C/Ctrl+V copia e cola · Del apaga · W fio · roda: zoom · botão do meio ou Alt+arrastar: mover a vista"}
        </span>
        <button type="button" className="secondary small-btn" onClick={fit}>
          Enquadrar
        </button>
      </div>
    </div>
  );
}
