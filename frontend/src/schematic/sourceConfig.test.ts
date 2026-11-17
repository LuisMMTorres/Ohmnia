import { describe, expect, it } from "vitest";
import { configureSource, sourceSettings, spiceNumber } from "./sourceConfig";
import type { Component } from "./types";
const source: Component = {
  id: "v1",
  ref: "V1",
  kind: "vdc",
  x: 0,
  y: 0,
  rot: 0,
  mirror: false,
  part_id: null,
  params: { dc: "5" },
};
describe("source waveform translation", () => {
  it("converts peak-to-peak amplitude to SPICE sine peak amplitude", () => {
    const sine = configureSource(source, {
      waveform: "sine",
      frequency: 2000,
      peakToPeak: 8,
      offset: -1,
      duty: 50,
    });
    expect(sine.params.amplitude).toBe("4");
    expect(sine.params.freq).toBe("2000");
    expect(sine.params.offset).toBe("-1");
    expect(sine.kind).toBe("vsin");
    expect(sine.id).toBe(source.id);
  });
  it("preserves square duty including edge times and triangular slopes", () => {
    const s = { waveform: "square" as const, frequency: 1000, peakToPeak: 4, offset: 1, duty: 25 };
    const square = configureSource(source, s);
    expect(Number(square.params.width) + Number(square.params.rise)).toBeCloseTo(0.00025, 12);
    expect(square.params.v1).toBe("-1");
    expect(square.params.v2).toBe("3");
    const triangle = configureSource({ ...source, kind: "idc" }, { ...s, waveform: "triangle" });
    expect(triangle.kind).toBe("ipulse");
    expect(triangle.params.width).toBe("0");
    expect(Number(triangle.params.rise)).toBeCloseTo(0.00025, 12);
    expect(Number(triangle.params.fall)).toBeCloseTo(0.00075, 12);
    expect(sourceSettings(triangle).waveform).toBe("triangle");
    expect(() => configureSource(source, { ...s, duty: 100 })).toThrow();
    expect(() => configureSource(source, { ...s, frequency: 0 })).toThrow();
  });
  it("reads engineering notation in legacy sources", () => {
    expect(
      sourceSettings({ ...source, kind: "vsin", params: { amplitude: "1", freq: "1k" } }).offset,
    ).toBe(0);
    expect(spiceNumber("2.5k")).toBe(2500);
    expect(spiceNumber("1meg")).toBe(1e6);
    expect(spiceNumber("3m")).toBe(0.003);
  });
});
