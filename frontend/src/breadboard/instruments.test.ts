import { expect, it } from "vitest";
import {
  addSupplyChannel,
  pruneOrphanSupplyLabels,
  removeSources,
  supplyAmpsText,
} from "./instruments";
import { emptySchematic, type Component, type Schematic } from "../schematic/types";
import { emptyBreadboard } from "./types";

it("removes all supply channels, generated labels, probes and mounted devices while preserving the circuit", () => {
  const component = (id: string, ref: string, bench = false): Component => ({
    id,
    ref,
    kind: "vdc",
    x: 0,
    y: 0,
    rot: 0,
    mirror: false,
    part_id: null,
    params: bench ? { bench_id: "PS1" } : {},
  });
  const original: Schematic = {
    ...emptySchematic(),
    components: [component("keep", "V1"), component("a", "V2", true), component("b", "V3", true)],
    labels: [
      { id: "PS1-p1", name: "ps1_ch1", x: 0, y: 0 },
      { id: "keep-label", name: "out", x: 5, y: 5 },
    ],
    probes: [
      { id: "keep-probe", kind: "v" as const, target: { net: "out" } },
      { id: "removed-current", kind: "i" as const, component: "V2" },
      { id: "removed-voltage", kind: "v" as const, target: { net: "ps1_ch1" } },
    ],
    breadboard: {
      ...emptyBreadboard(),
      parts: [
        { ref: "V1", package: "fonte-cc", legs: {} },
        { ref: "V2", package: "fonte-cc", legs: { p: "vp1" } },
      ],
    },
  };
  const result = removeSources(original, ["a", "b"]);
  expect(result.components.map((c) => c.ref)).toEqual(["V1"]);
  expect(result.labels.map((l) => l.name)).toEqual(["out"]);
  expect(result.probes.map((p) => p.id)).toEqual(["keep-probe"]);
  expect(result.breadboard?.parts.map((p) => p.ref)).toEqual(["V1"]);
  expect(original.components).toHaveLength(3);
});

it("uses one or two supply channels without removing the other channel's connections or probes", () => {
  const one = addSupplyChannel(emptySchematic(), "PS1", 1);
  const two = addSupplyChannel(one, "PS1", 2);
  const first = two.components.find((c) => c.params.bench_channel === "1")!;
  const remaining = removeSources(two, [first.id]);
  expect(remaining.components).toHaveLength(1);
  expect(remaining.labels.map((l) => l.name)).toContain("PS1_ch2");
  expect(remaining.probes.some((p) => p.target?.net === "PS1_ch2")).toBe(true);
  expect(remaining.probes.some((p) => p.target?.net === "PS1_ch1")).toBe(false);
  const restored = addSupplyChannel(remaining, "PS1", 1);
  expect(restored.components).toHaveLength(2);
  expect(new Set(restored.components.map((c) => c.ref)).size).toBe(2);
  expect(addSupplyChannel(restored, "PS1", 1)).toBe(restored);
});

it("cleans old generated tags without deleting manual labels or tags of surviving channels", () => {
  const supply = addSupplyChannel(addSupplyChannel(emptySchematic(), "PS1", 1), "PS1", 2);
  const broken = {
    ...supply,
    components: supply.components.filter((c) => c.params.bench_channel !== "1"),
    labels: [
      ...supply.labels,
      { id: "manual", name: "PS1_ch1", x: 10, y: 10 },
      { id: "manual-ground", name: "0", x: 20, y: 20 },
    ],
  };
  const cleaned = pruneOrphanSupplyLabels(broken);
  expect(cleaned.labels.some((l) => l.id === "PS1-p1" || l.id === "PS1-n1")).toBe(false);
  expect(cleaned.labels.some((l) => l.id === "PS1-p2")).toBe(true);
  expect(cleaned.labels.some((l) => l.id === "manual")).toBe(true);
  expect(cleaned.labels.some((l) => l.id === "manual-ground")).toBe(true);
  expect(pruneOrphanSupplyLabels(cleaned)).toBe(cleaned);
});

it("shows the current the supply delivers, from the branch current of the source", () => {
  expect(supplyAmpsText(undefined)).toBe("-.---");
  expect(supplyAmpsText(NaN)).toBe("-.---");
  // ngspice: a source delivering 12,3 mA has i(v1) = −12,3 mA
  expect(supplyAmpsText(-0.0123)).toBe("0,012");
  expect(supplyAmpsText(-1.5)).toBe("1,500");
  expect(supplyAmpsText(-12.345)).toBe("12,35");
  expect(supplyAmpsText(0.25)).toBe("-0,250");
  expect(supplyAmpsText(1e-9)).toBe("0,000");
});
