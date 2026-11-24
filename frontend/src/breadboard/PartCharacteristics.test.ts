import { describe, expect, it } from "vitest";
import { circuitRows } from "./PartCharacteristics";
import type { Component, SymbolDef } from "../schematic/types";

const def = {
  kind: "r",
  label: "Resistor",
  params: [
    { name: "value", label: "Resistência", unit: "Ω", default: "1k", type: "number" },
    { name: "tol", label: "Tolerância", unit: "%", default: "", type: "number" },
  ],
} as unknown as SymbolDef;

const comp = (params: Record<string, string>): Component => ({
  id: "c1",
  kind: "r",
  ref: "R1",
  x: 0,
  y: 0,
  rot: 0,
  mirror: false,
  params,
  part_id: null,
});

describe("circuitRows", () => {
  it("labels the values with the symbol's names and units, defaults included", () => {
    expect(circuitRows(comp({ tol: "5" }), def)).toEqual([
      { label: "Resistência", value: "1k Ω" },
      { label: "Tolerância", value: "5 %" },
    ]);
  });

  it("hides the bench wiring and keeps unknown parameters by key", () => {
    const rows = circuitRows(comp({ value: "2k2", bench_id: "b1", extra: "x" }), def);
    expect(rows).toEqual([
      { label: "Resistência", value: "2k2 Ω" },
      { label: "extra", value: "x" },
    ]);
  });

  it("works without the symbol library", () => {
    expect(circuitRows(comp({ value: "10k" }), undefined)).toEqual([
      { label: "value", value: "10k" },
    ]);
  });
});
