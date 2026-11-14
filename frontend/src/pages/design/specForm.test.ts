import { describe, expect, it } from "vitest";
import type { JsonSchema } from "../../api";
import {
  fieldsFromSchema,
  resample,
  resampleLog,
  sliderRange,
  sliderStep,
  tracePeriod,
  visible,
} from "./specForm";

const SCHEMA: JsonSchema = {
  $defs: { QuantityModel: { type: "object" } },
  properties: {
    topology: { enum: ["meia_onda", "ponte"], type: "string" },
    pulses: { enum: [3, 6, 12], type: "integer" },
    Vo: { $ref: "#/$defs/QuantityModel" },
    ripple_pct: { type: "number", exclusiveMinimum: 0, maximum: 50 },
    controlled: { type: "boolean" },
  },
};
const DEFAULTS = {
  topology: "ponte",
  pulses: 6,
  Vo: { value: 12, unit: "V" },
  ripple_pct: 5,
  controlled: true,
};

describe("fieldsFromSchema", () => {
  it("maps each property to a field kind, in schema order", () => {
    const f = fieldsFromSchema(SCHEMA, DEFAULTS);
    expect(f.map((x) => [x.key, x.kind])).toEqual([
      ["topology", "enum"],
      ["pulses", "enum"],
      ["Vo", "quantity"],
      ["ripple_pct", "number"],
      ["controlled", "bool"],
    ]);
    expect(f[2]).toMatchObject({ unit: "V" });
    expect(f[3]).toMatchObject({ min: 0, max: 50 });
  });
});

describe("sliders", () => {
  it("uses schema bounds, else a quarter to four times the default", () => {
    expect(sliderRange({ key: "r", kind: "number", min: 0, max: 50 }, 5)).toEqual([0, 50]);
    expect(sliderRange({ key: "Vo", kind: "quantity", unit: "V" }, 12)).toEqual([3, 48]);
  });
  it("rounds the step to 1, 2 or 5 × 10ⁿ", () => {
    expect(sliderStep(0, 50)).toBeCloseTo(0.2);
    expect(sliderStep(3, 48)).toBeCloseTo(0.2);
    expect(sliderStep(0, 1000)).toBeCloseTo(5);
  });
});

describe("visible", () => {
  it("hides fields that do not apply to the chosen topology", () => {
    expect(visible("DM-RET1", "L_factor", { filter: "C" })).toBe(false);
    expect(visible("DM-RET1", "L_factor", { filter: "LC" })).toBe(true);
    expect(visible("DM-RETC1", "freewheel", { topology: "ponte" })).toBe(false);
    expect(visible("DM-RET3", "alpha_nom", { controlled: false })).toBe(false);
  });
});

describe("resample", () => {
  it("interpolates linearly onto the output grid", () => {
    expect(resample([0, 1, 2], [0, 10, 20], [0, 0.5, 1.5, 2])).toEqual([0, 5, 15, 20]);
  });
});

describe("tracePeriod", () => {
  it("uses trace_period when given", () => {
    expect(tracePeriod({ value: 2, unit: "ms" }, { value: 60, unit: "Hz" })).toBeCloseTo(2e-3);
  });
  it("falls back to one period of spec.f", () => {
    expect(tracePeriod(null, { value: 1, unit: "kHz" })).toBeCloseTo(1e-3);
    expect(tracePeriod(undefined, undefined)).toBeCloseTo(1 / 60);
  });
});

describe("resampleLog", () => {
  it("interpolates in log frequency", () => {
    expect(resampleLog([10, 1000], [0, 2], [100])[0]).toBeCloseTo(1);
  });
});

describe("visible (Phase 4)", () => {
  it("hides fields that do not apply", () => {
    expect(visible("DM-FORMA", "stages", { kind: "grampeador" })).toBe(false);
    expect(visible("DM-FORMA", "C", { kind: "grampeador" })).toBe(true);
    expect(visible("DM-BIAS", "R_gate", { config: "divisor" })).toBe(false);
    expect(visible("DM-CHAVE", "overdrive", { device: "mosfet" })).toBe(false);
    expect(visible("DM-CHAVE", "overdrive", { device: "darlington" })).toBe(true);
    expect(visible("DM-BIAS", "R_gate", { config: "jfet_auto" })).toBe(true);
    expect(visible("DM-BIAS", "kE", { config: "jfet_auto" })).toBe(false);
    expect(visible("DM-BIAS", "kE", { config: "jfet_divisor" })).toBe(true);
    expect(visible("DM-BIAS", "beta_ideal", { config: "jfet_divisor" })).toBe(false);
    expect(visible("DM-SSA", "VBE", { config: "FCJ" })).toBe(false);
    expect(visible("DM-SSA", "Av", { config: "FCJ" })).toBe(true);
    expect(visible("DM-PA", "darlington", { cls: "A" })).toBe(false);
    expect(visible("DM-PA", "darlington", { cls: "B" })).toBe(true);
    expect(visible("DM-ZEN", "beta_ideal", { variant: "transistor" })).toBe(true);
  });
});

describe("visible (Phase 5)", () => {
  it("shows only the fields of the chosen configuration", () => {
    expect(visible("DM-OPA", "Rt", { config: "inversor" })).toBe(false);
    expect(visible("DM-OPA", "Rt", { config: "transimpedancia" })).toBe(true);
    expect(visible("DM-FIL", "B", { kind: "passa_baixas" })).toBe(false);
    expect(visible("DM-FIL", "ripple_db", { approx: "chebyshev" })).toBe(true);
    expect(visible("DM-FIL", "R0", { realization: "passivo_lc" })).toBe(true);
    expect(visible("DM-OPNL", "Rp", { config: "comparador", device: "comparador" })).toBe(true);
    expect(visible("DM-OPNL", "Vlim", {})).toBe(false);
    expect(visible("DM-OSC", "RC_tbj", { config: "multivibrador_tbj" })).toBe(true);
    expect(visible("DM-OSC", "duty", {})).toBe(false);
    expect(visible("DM-INST", "x_max", { config: "ponte_wheatstone" })).toBe(true);
    expect(visible("DM-INST", "V_fs", { config: "transmissor_4_20" })).toBe(false);
  });
});
