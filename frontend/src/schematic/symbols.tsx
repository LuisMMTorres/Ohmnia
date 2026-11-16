/** SVG drawings of the library symbols, in local coordinates (grid units × GRID px). */
import type { ReactNode } from "react";
import { GRID, pinDefs } from "./geometry";
import type { Component, SymbolDef } from "./types";

const G = GRID;
const u = (n: number) => n * G;

function line(x1: number, y1: number, x2: number, y2: number, key?: string): ReactNode {
  return <line key={key} x1={u(x1)} y1={u(y1)} x2={u(x2)} y2={u(y2)} />;
}
function poly(points: [number, number][], key?: string, fill = false): ReactNode {
  return (
    <polyline
      key={key}
      points={points.map(([x, y]) => `${u(x)},${u(y)}`).join(" ")}
      className={fill ? "fill" : undefined}
    />
  );
}
function text(x: number, y: number, t: string, size = 0.7, key?: string): ReactNode {
  return (
    <text
      key={key}
      x={u(x)}
      y={u(y)}
      fontSize={u(size)}
      textAnchor="middle"
      dominantBaseline="central"
      className="sym-text"
    >
      {t}
    </text>
  );
}
function circle(x: number, y: number, r: number, key?: string): ReactNode {
  return <circle key={key} cx={u(x)} cy={u(y)} r={u(r)} />;
}

function zigzag(x0: number, x1: number): ReactNode {
  const n = 6;
  const pts: [number, number][] = [[x0, 0]];
  for (let i = 0; i < n; i++) pts.push([x0 + ((i + 0.5) * (x1 - x0)) / n, i % 2 ? 0.35 : -0.35]);
  pts.push([x1, 0]);
  return poly(pts, "z");
}

function coil(x0: number, x1: number, vertical = false, offset = 0): ReactNode {
  const n = 4;
  const w = (x1 - x0) / n;
  let d = `M ${vertical ? u(offset) : u(x0)} ${vertical ? u(x0) : u(offset)}`;
  for (let i = 0; i < n; i++) {
    const a = x0 + (i + 1) * w;
    d += vertical
      ? ` A ${u(w / 2)} ${u(w / 2)} 0 0 1 ${u(offset)} ${u(a)}`
      : ` A ${u(w / 2)} ${u(w / 2)} 0 0 1 ${u(a)} ${u(offset)}`;
  }
  return <path key="coil" d={d} />;
}

function sourceBody(kind: string): ReactNode[] {
  const current = kind.startsWith("i");
  const out: ReactNode[] = [line(0, -2, 0, -1, "a"), line(0, 1, 0, 2, "b"), circle(0, 0, 1, "c")];
  if (current) {
    out.push(
      line(0, -0.6, 0, 0.6, "arr"),
      poly(
        [
          [-0.3, 0.25],
          [0, 0.6],
          [0.3, 0.25],
        ],
        "head",
      ),
    );
    return out;
  }
  const w = kind.slice(1);
  if (w === "dc") out.push(text(0, -0.45, "+", 0.8, "p"), text(0, 0.45, "−", 0.8, "m"));
  if (w === "sin") {
    out.push(
      <path key="w" d={`M ${u(-0.6)} 0 Q ${u(-0.3)} ${u(-0.8)} 0 0 T ${u(0.6)} 0`} fill="none" />,
    );
  }
  if (w === "pulse")
    out.push(
      poly(
        [
          [-0.6, 0.3],
          [-0.3, 0.3],
          [-0.3, -0.3],
          [0.3, -0.3],
          [0.3, 0.3],
          [0.6, 0.3],
        ],
        "w",
      ),
    );
  if (w === "pwl")
    out.push(
      poly(
        [
          [-0.6, 0.3],
          [-0.2, -0.4],
          [0.1, 0.1],
          [0.6, -0.3],
        ],
        "w",
      ),
    );
  return out;
}

function diamond(cx: number, cy: number, r: number, key: string): ReactNode {
  return poly(
    [
      [cx, cy - r],
      [cx + r, cy],
      [cx, cy + r],
      [cx - r, cy],
      [cx, cy - r],
    ],
    key,
  );
}

function bjt(pnp: boolean, igbt = false): ReactNode[] {
  const out: ReactNode[] = [
    line(-2, 0, igbt ? -0.9 : -0.6, 0, "b"),
    line(-0.6, -0.8, -0.6, 0.8, "bar"),
    poly(
      [
        [-0.6, -0.4],
        [0, -1.1],
        [0, -2],
      ],
      "c",
    ),
    poly(
      [
        [-0.6, 0.4],
        [0, 1.1],
        [0, 2],
      ],
      "e",
    ),
    circle(-0.2, 0, 1.25, "o"),
  ];
  if (igbt) out.push(line(-0.9, -0.6, -0.9, 0.6, "g"));
  // emitter arrow: out of the transistor (NPN) or into it (PNP)
  out.push(
    pnp
      ? poly(
          [
            [-0.2, 0.55],
            [-0.5, 0.48],
            [-0.37, 0.78],
          ],
          "arr",
        )
      : poly(
          [
            [-0.25, 0.95],
            [0, 1.1],
            [-0.05, 0.8],
          ],
          "arr",
        ),
  );
  return out;
}

function fet(kind: string): ReactNode[] {
  const jfet = kind.endsWith("jf");
  const pType = kind.startsWith("p");
  const out: ReactNode[] = [];
  if (jfet) {
    out.push(
      line(-2, 0.4, -0.5, 0.4, "g"),
      line(-0.5, -0.9, -0.5, 0.9, "ch"),
      poly(
        [
          [-0.5, -0.6],
          [0, -0.6],
          [0, -2],
        ],
        "d",
      ),
      poly(
        [
          [-0.5, 0.6],
          [0, 0.6],
          [0, 2],
        ],
        "s",
      ),
      pType
        ? poly(
            [
              [-1.0, 0.2],
              [-1.3, 0.4],
              [-1.0, 0.6],
            ],
            "arr",
          )
        : poly(
            [
              [-0.8, 0.2],
              [-0.5, 0.4],
              [-0.8, 0.6],
            ],
            "arr",
          ),
    );
  } else {
    out.push(
      line(-2, 0, -0.9, 0, "g"),
      line(-0.9, -0.7, -0.9, 0.7, "gb"),
      line(-0.55, -0.9, -0.55, -0.3, "c1"),
      line(-0.55, -0.15, -0.55, 0.15, "c2"),
      line(-0.55, 0.3, -0.55, 0.9, "c3"),
      poly(
        [
          [-0.55, -0.6],
          [0, -0.6],
          [0, -2],
        ],
        "d",
      ),
      poly(
        [
          [-0.55, 0.6],
          [0, 0.6],
          [0, 2],
        ],
        "s",
      ),
      line(-0.55, 0, 0, 0, "body"),
      line(0, 0, 0, 0.6, "bs"),
      pType
        ? poly(
            [
              [-0.15, -0.15],
              [0, 0],
              [-0.15, 0.15],
            ],
            "arr",
          )
        : poly(
            [
              [-0.3, -0.15],
              [-0.5, 0],
              [-0.3, 0.15],
            ],
            "arr",
          ),
    );
  }
  return out;
}

function thyristor(triac: boolean): ReactNode[] {
  const out: ReactNode[] = [line(0, -2, 0, -0.6, "a"), line(0, 0.6, 0, 2, "k")];
  out.push(
    poly(
      [
        [-0.6, -0.6],
        [0.6, -0.6],
        [0, 0.6],
        [-0.6, -0.6],
      ],
      "t1",
    ),
    line(-0.7, 0.6, 0.7, 0.6, "bar"),
  );
  if (triac)
    out.push(
      line(-0.7, -0.6, 0.7, -0.6, "bar2"),
      poly(
        [
          [-0.6, 0.6],
          [0.6, 0.6],
          [0, -0.6],
          [-0.6, 0.6],
        ],
        "t2",
      ),
    );
  out.push(
    poly(
      [
        [-2, 1],
        [-0.5, 1],
        [-0.2, 0.6],
      ],
      "g",
    ),
  );
  return out;
}

export function SymbolBody({ c, sym }: { c: Component; sym: SymbolDef | undefined }) {
  const k = c.kind;
  let body: ReactNode[] = [];
  if (k === "resistor")
    body = [line(-2, 0, -1.2, 0, "a"), zigzag(-1.2, 1.2), line(1.2, 0, 2, 0, "b")];
  else if (k === "capacitor")
    body = [
      line(-2, 0, -0.25, 0, "a"),
      line(-0.25, -0.8, -0.25, 0.8, "p1"),
      line(0.25, -0.8, 0.25, 0.8, "p2"),
      line(0.25, 0, 2, 0, "b"),
    ];
  else if (k === "inductor")
    body = [line(-2, 0, -1.4, 0, "a"), coil(-1.4, 1.4), line(1.4, 0, 2, 0, "b")];
  else if (k === "rl_load")
    body = [
      line(-2, 0, -1.6, 0, "a"),
      <rect key="r" x={u(-1.6)} y={u(-0.4)} width={u(1.4)} height={u(0.8)} />,
      line(-0.2, 0, 0, 0, "m"),
      coil(0, 1.6),
      line(1.6, 0, 2, 0, "b"),
    ];
  else if (k === "transformer")
    body = [
      poly(
        [
          [-2, -2],
          [-1, -2],
          [-1, -1.4],
        ],
        "p1",
      ),
      poly(
        [
          [-2, 2],
          [-1, 2],
          [-1, 1.4],
        ],
        "p2",
      ),
      poly(
        [
          [2, -2],
          [1, -2],
          [1, -1.4],
        ],
        "s1",
      ),
      poly(
        [
          [2, 2],
          [1, 2],
          [1, 1.4],
        ],
        "s2",
      ),
      <g key="cp">{coil(-1.4, 1.4, true, -1)}</g>,
      <g key="cs" transform={`translate(${u(2)},0) scale(-1,1)`}>
        {coil(-1.4, 1.4, true, 1)}
      </g>,
      line(-0.15, -1.5, -0.15, 1.5, "k1"),
      line(0.15, -1.5, 0.15, 1.5, "k2"),
      <circle key="d1" cx={u(-1.5)} cy={u(-1.3)} r={u(0.12)} className="fill" />,
      <circle key="d2" cx={u(1.5)} cy={u(-1.3)} r={u(0.12)} className="fill" />,
    ];
  else if (/^[vi](dc|sin|pulse|pwl)$/.test(k)) body = sourceBody(k);
  else if (k === "v3ph")
    body = [
      circle(0, 0, 1.2, "o"),
      text(0, 0, "3~", 0.8, "t"),
      line(-2, 0, -1.2, 0, "n"),
      poly(
        [
          [0.85, -0.85],
          [1.2, -2],
          [2, -2],
        ],
        "a",
      ),
      line(1.2, 0, 2, 0, "b"),
      poly(
        [
          [0.85, 0.85],
          [1.2, 2],
          [2, 2],
        ],
        "c",
      ),
    ];
  else if (k === "bsource")
    body = [
      line(0, -2, 0, -1, "a"),
      line(0, 1, 0, 2, "b"),
      diamond(0, 0, 1, "d"),
      text(0, 0, "B", 0.8, "t"),
    ];
  else if (k === "vcvs" || k === "vccs")
    body = [
      line(2, -2, 2, -1, "a"),
      line(2, 1, 2, 2, "b"),
      diamond(2, 0, 1, "d"),
      text(2, 0, k === "vcvs" ? "E" : "G", 0.7, "t"),
      line(-2, -2, -1, -2, "cp"),
      line(-2, 2, -1, 2, "cn"),
      text(-0.6, -2, "+", 0.7, "pp"),
      text(-0.6, 2, "−", 0.7, "pn"),
    ];
  else if (k === "cccs" || k === "ccvs")
    body = [
      line(0, -2, 0, -1, "a"),
      line(0, 1, 0, 2, "b"),
      diamond(0, 0, 1, "d"),
      text(0, 0, k === "cccs" ? "F" : "H", 0.7, "t"),
    ];
  else if (k === "diode" || k === "zener") {
    body = [
      line(-2, 0, -0.6, 0, "a"),
      line(0.6, 0, 2, 0, "b"),
      poly(
        [
          [-0.6, -0.7],
          [-0.6, 0.7],
          [0.6, 0],
          [-0.6, -0.7],
        ],
        "t",
      ),
      k === "zener"
        ? poly(
            [
              [0.35, -0.85],
              [0.6, -0.7],
              [0.6, 0.7],
              [0.85, 0.85],
            ],
            "bar",
          )
        : line(0.6, -0.7, 0.6, 0.7, "bar"),
    ];
  } else if (k === "npn" || k === "pnp") body = bjt(k === "pnp");
  else if (k === "igbt") body = bjt(false, true);
  else if (["nmos", "pmos", "njf", "pjf"].includes(k)) body = fet(k);
  else if (k === "opamp")
    body = [
      poly(
        [
          [-2, -2],
          [-2, 2],
          [2, 0],
          [-2, -2],
        ],
        "t",
      ),
      line(-3, -1, -2, -1, "n"),
      line(-3, 1, -2, 1, "p"),
      line(2, 0, 3, 0, "o"),
      text(-1.5, -1, "−", 0.8, "mn"),
      text(-1.5, 1, "+", 0.8, "mp"),
    ];
  else if (k === "switch")
    body = [
      line(-2, 0, -1, 0, "a"),
      line(1, 0, 2, 0, "b"),
      circle(-1, 0, 0.12, "c1"),
      circle(1, 0, 0.12, "c2"),
      line(-1, 0, 0.85, -0.7, "blade"),
      line(-1, 2, -1, 1.2, "cp"),
      line(1, 2, 1, 1.2, "cn"),
      <rect key="box" x={u(-1.2)} y={u(0.6)} width={u(2.4)} height={u(0.6)} className="thin" />,
      text(-0.6, 0.9, "+", 0.5, "pp"),
    ];
  else if (k === "scr" || k === "triac") body = thyristor(k === "triac");
  else if (k === "ground")
    body = [
      line(0, 0, 0, 0.6, "a"),
      line(-0.8, 0.6, 0.8, 0.6, "b1"),
      line(-0.5, 0.9, 0.5, 0.9, "b2"),
      line(-0.2, 1.2, 0.2, 1.2, "b3"),
    ];
  else if (k === "subckt") {
    const pins = pinDefs(c, sym);
    const rows = Math.max(1, ...pins.map((p) => p.dy / 2 + 1));
    body = [
      <rect key="box" x={u(-2)} y={u(-1)} width={u(4)} height={u(2 * rows)} />,
      ...pins.map((p) => line(p.dx, p.dy, p.dx < 0 ? -2 : 2, p.dy, `l${p.name}`)),
      ...pins.map((p) => (
        <text
          key={`t${p.name}`}
          x={u(p.dx < 0 ? -1.8 : 1.8)}
          y={u(p.dy)}
          fontSize={u(0.55)}
          textAnchor={p.dx < 0 ? "start" : "end"}
          dominantBaseline="central"
          className="sym-text"
        >
          {p.name}
        </text>
      )),
      text(0, rows - 1, c.params.model || "X", 0.6, "name"),
    ];
  } else if (sym && MODULE_GROUPS.has(sym.group)) body = moduleBox(c, sym);
  else body = [<rect key="box" x={u(-2)} y={u(-1)} width={u(4)} height={u(2)} />];
  return <>{body}</>;
}

// Controllers, sensors and actuators (Fase 11): a box with its pins named and a short title.
const MODULE_GROUPS = new Set(["Controladores", "Sensores", "Atuadores"]);
const SHORT: Record<string, string> = {
  arduino_uno: "Arduino Uno",
  esp32_devkitc: "ESP32",
  plc: "CLP",
  lm35: "LM35",
  pt100: "Pt100",
  tx420: "4-20 mA",
  acs712: "ACS712",
  potentiometer: "POT",
  relay: "RELÉ",
  dc_motor: "M",
  heater: "AQUEC.",
  switch_manual: "BOTÃO",
  pump_plant: "INV+BOMBA",
};

function moduleBox(c: Component, sym: SymbolDef): ReactNode[] {
  const pins = pinDefs(c, sym);
  const xs = pins.map((p) => p.dx);
  const ys = pins.map((p) => p.dy);
  const side = pins.some((p) => p.dx !== 0);
  const left = side && Math.min(...xs) < 0 ? Math.min(...xs) + 1 : -1.6;
  const right = side && Math.max(...xs) > 0 ? Math.max(...xs) - 1 : 1.6;
  const vert = pins.filter((p) => p.dx === 0);
  const top = vert.some((p) => p.dy < 0) ? Math.min(...ys) + 1 : Math.min(...ys) - 1;
  const bottom = vert.some((p) => p.dy > 0) ? Math.max(...ys) - 1 : Math.max(...ys) + 1;
  const many = pins.length > 2 || pins.some((p) => !/^\d$/.test(p.name));
  return [
    <rect
      key="box"
      x={u(left)}
      y={u(top)}
      width={u(right - left)}
      height={u(bottom - top)}
      rx={u(0.2)}
      className={
        c.kind === "plc" || c.kind.includes("arduino") || c.kind.includes("esp32") ? "board" : ""
      }
    />,
    ...pins.map((p) =>
      p.dx === 0
        ? line(p.dx, p.dy, 0, p.dy < 0 ? top : bottom, `l${p.name}`)
        : line(p.dx, p.dy, p.dx < 0 ? left : right, p.dy, `l${p.name}`),
    ),
    ...(many
      ? pins.map((p) => (
          <text
            key={`t${p.name}`}
            x={u(p.dx < 0 ? left + 0.2 : p.dx > 0 ? right - 0.2 : 0)}
            y={u(p.dx === 0 ? (p.dy < 0 ? top + 0.5 : bottom - 0.5) : p.dy)}
            fontSize={u(0.55)}
            textAnchor={p.dx < 0 ? "start" : p.dx > 0 ? "end" : "middle"}
            dominantBaseline="central"
            className="sym-text"
          >
            {p.name}
          </text>
        ))
      : []),
    text(
      (left + right) / 2,
      pins.length > 6 ? top + 0.8 : (top + bottom) / 2,
      SHORT[c.kind] ?? sym.label,
      pins.length > 6 ? 0.7 : 0.55,
      "name",
    ),
  ];
}

const UNIT: Record<string, string> = {
  resistor: "Ω",
  capacitor: "F",
  inductor: "H",
};

/** Short value text shown next to the symbol. */
export function valueText(c: Component, sym: SymbolDef | undefined): string {
  if (c.part_id) return c.params.part_label ?? "catálogo";
  const p = (name: string) =>
    c.params[name] ?? sym?.params.find((d) => d.name === name)?.default ?? "";
  if (c.kind in UNIT) return `${p("value")}${UNIT[c.kind]}`;
  if (c.kind === "vdc" || c.kind === "idc") return `${p("dc")}${c.kind[0] === "v" ? "V" : "A"}`;
  if (c.kind.endsWith("sin")) return `${p("amplitude")} @ ${p("freq")}Hz`;
  if (c.kind.endsWith("pulse")) return `${p("v1")}→${p("v2")}, T ${p("period")}`;
  if (c.kind === "v3ph") return `${p("vrms")}V ${p("freq")}Hz`;
  if (c.kind === "rl_load") return `${p("r")}Ω + ${p("l")}H`;
  if (c.kind === "transformer") return `1:${p("n")}`;
  if (c.kind === "zener") return `${p("vz")}V`;
  if (c.kind === "bsource") return p("expr");
  if (c.kind === "subckt") return "";
  if (c.params.model) return c.params.model;
  return "";
}
