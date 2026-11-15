/** Example schematics for the editor (generic didactic models, no catalogue data). */
import { emptySchematic, type Component, type Schematic } from "./types";

let n = 0;
function c(
  kind: string,
  ref: string,
  x: number,
  y: number,
  rot: Component["rot"] = 0,
  params: Record<string, string> = {},
): Component {
  n += 1;
  return { id: `ex${n}`, kind, ref, x, y, rot, mirror: false, params, part_id: null };
}
function w(...points: [number, number][]) {
  n += 1;
  return { id: `exw${n}`, points };
}
function l(name: string, x: number, y: number) {
  n += 1;
  return { id: `exl${n}`, name, x, y };
}

function rc(): Schematic {
  return {
    ...emptySchematic(),
    title: "Filtro RC passa-baixas (fc ≈ 1 kHz)",
    components: [
      c("vsin", "V1", 0, 0, 0, { amplitude: "1", freq: "1k" }),
      c("resistor", "R1", 4, -4, 0, { value: "1k" }),
      c("capacitor", "C1", 10, 0, 90, { value: "159n" }),
      c("ground", "GND1", 0, 4),
      c("ground", "GND2", 10, 4),
    ],
    wires: [
      w([0, -2], [0, -4], [2, -4]),
      w([6, -4], [10, -4], [10, -2]),
      w([0, 2], [0, 4]),
      w([10, 2], [10, 4]),
    ],
    labels: [l("in", 0, -4), l("out", 10, -4)],
    probes: [
      { id: "pin", kind: "v", target: { net: "in" } },
      { id: "pout", kind: "v", target: { net: "out" } },
      { id: "pi", kind: "i", component: "C1", pin: "1" },
    ],
    analyses: [
      { kind: "tran", params: { tstop: "5m", tmax: "5u" }, enabled: true },
      {
        kind: "ac",
        params: { variation: "dec", points: "50", fstart: "10", fstop: "1meg" },
        enabled: true,
      },
    ],
  };
}

function ce(): Schematic {
  return {
    ...emptySchematic(),
    title: "Amplificador emissor comum",
    components: [
      c("vdc", "VCC", 24, 4, 0, { dc: "12" }),
      c("ground", "GND1", 24, 8),
      c("resistor", "R1", 8, -2, 90, { value: "47k" }),
      c("resistor", "R2", 8, 6, 90, { value: "10k" }),
      c("ground", "GND2", 8, 8),
      c("npn", "Q1", 12, 2, 0, { bf: "150" }),
      c("resistor", "RC", 12, -4, 90, { value: "2.2k" }),
      c("resistor", "RE", 12, 8, 90, { value: "1k" }),
      c("ground", "GND3", 12, 10),
      c("capacitor", "CE", 16, 8, 90, { value: "100u", tol: "20" }),
      c("ground", "GND4", 16, 10),
      c("capacitor", "C1", 4, 2, 0, { value: "10u", tol: "20" }),
      c("vsin", "VIN", 0, 6, 0, { amplitude: "10m", freq: "1k" }),
      c("ground", "GND5", 0, 8),
    ],
    wires: [
      w([24, 6], [24, 8]),
      w([8, 0], [8, 4]),
      w([6, 2], [8, 2]),
      w([8, 2], [10, 2]),
      w([12, -2], [12, 0]),
      w([12, 4], [12, 6]),
      w([12, 6], [16, 6]),
      w([0, 4], [0, 2], [2, 2]),
    ],
    labels: [l("vcc", 24, 2), l("vcc", 8, -4), l("vcc", 12, -6), l("c", 12, -2), l("in", 0, 2)],
    probes: [
      { id: "pin", kind: "v", target: { net: "in" } },
      { id: "pc", kind: "v", target: { net: "c" } },
      { id: "pq", kind: "p", component: "Q1" },
    ],
    analyses: [
      { kind: "op", params: {}, enabled: true },
      { kind: "tran", params: { tstop: "5m", tmax: "5u" }, enabled: true },
      {
        kind: "ac",
        params: { variation: "dec", points: "30", fstart: "10", fstop: "10meg" },
        enabled: true,
      },
    ],
  };
}

function bridge(): Schematic {
  return {
    ...emptySchematic(),
    title: "Retificador monofásico em ponte com filtro capacitivo",
    components: [
      c("vsin", "V1", 0, 0, 0, { amplitude: "17", freq: "60", ac: "0" }),
      c("diode", "D1", 8, -6),
      c("diode", "D2", 8, -2),
      c("diode", "D3", 8, 2),
      c("diode", "D4", 8, 6),
      c("capacitor", "C1", 16, 0, 90, { value: "470u", tol: "20" }),
      c("resistor", "RL", 20, 0, 90, { value: "100" }),
      c("ground", "GND1", 16, 2),
      c("ground", "GND2", 20, 2),
    ],
    wires: [w([16, -2], [20, -2])],
    labels: [
      l("a", 0, -2),
      l("b", 0, 2),
      l("a", 6, -6),
      l("p", 10, -6),
      l("b", 6, -2),
      l("p", 10, -2),
      l("0", 6, 2),
      l("a", 10, 2),
      l("0", 6, 6),
      l("b", 10, 6),
      l("p", 16, -2),
    ],
    probes: [
      { id: "pp", kind: "v", target: { net: "p" } },
      { id: "pab", kind: "vdiff", target: { net: "a" }, reference: { net: "b" } },
      { id: "pi", kind: "i", component: "V1", pin: "p" },
    ],
    analyses: [{ kind: "tran", params: { tstop: "100m", tmax: "20u" }, enabled: true }],
  };
}

function rcMonteCarlo(): Schematic {
  const s = rc();
  return {
    ...s,
    title: "Filtro RC: Monte Carlo com R ±5 % e C ±10 %",
    analyses: [
      {
        kind: "ac",
        params: { variation: "dec", points: "50", fstart: "10", fstop: "1meg" },
        enabled: true,
      },
    ],
    sweep: { ...s.sweep, kind: "montecarlo", runs: 50, seed: 1, distribution: "gauss" },
  };
}

function rlcStep(): Schematic {
  return {
    ...emptySchematic(),
    title: "RLC série: resposta ao degrau com STEP de R",
    components: [
      c("vpulse", "V1", 0, 0, 0, {
        v1: "0",
        v2: "1",
        delay: "0.1m",
        rise: "1n",
        fall: "1n",
        width: "10m",
        period: "20m",
      }),
      c("resistor", "R1", 4, -4, 0, { value: "20" }),
      c("inductor", "L1", 10, -4, 0, { value: "10m" }),
      c("capacitor", "C1", 14, 0, 90, { value: "1u" }),
      c("ground", "GND1", 0, 4),
      c("ground", "GND2", 14, 4),
    ],
    wires: [
      w([0, -2], [0, -4], [2, -4]),
      w([6, -4], [8, -4]),
      w([12, -4], [14, -4], [14, -2]),
      w([0, 2], [0, 4]),
      w([14, 2], [14, 4]),
    ],
    labels: [l("out", 14, -4)],
    probes: [{ id: "po", kind: "v", target: { net: "out" } }],
    analyses: [{ kind: "tran", params: { tstop: "3m", tmax: "2u" }, enabled: true }],
    sweep: {
      kind: "step",
      target: "R1.value",
      spacing: "list",
      values: ["20", "60", "200"],
      runs: 30,
      seed: 1,
      distribution: "gauss",
    },
  };
}

export const SCHEMATIC_EXAMPLES: Record<string, () => Schematic> = {
  "Filtro RC passa-baixas": rc,
  "Amplificador emissor comum": ce,
  "Retificador em ponte com filtro": bridge,
  "Filtro RC: Monte Carlo": rcMonteCarlo,
  "RLC série: STEP de R": rlcStep,
};
