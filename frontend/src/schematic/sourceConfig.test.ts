import { describe, expect, it } from "vitest";
import {
  configureSource,
  peakToPeakFromRms,
  rmsFromPeakToPeak,
  sourceSettings,
  spiceNumber,
} from "./sourceConfig";
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
  it("converts the RMS value to the SPICE sine peak amplitude (Vp = Vrms·√2)", () => {
    const sine = configureSource(source, {
      waveform: "sine",
      frequency: 2000,
      rms: 127,
      offset: -1,
      duty: 50,
    });
    expect(Number(sine.params.amplitude)).toBeCloseTo(127 * Math.SQRT2, 9);
    expect(sine.params.bench_vrms).toBe("127");
    expect(sine.params.freq).toBe("2000");
    expect(sine.params.offset).toBe("-1");
    expect(sine.kind).toBe("vsin");
    expect(sine.id).toBe(source.id);
  });
  it("preserves square duty including edge times and triangular slopes", () => {
    // square, D = 25 %: Vrms = Vpp·√(D(1−D)) → Vpp = 4 V for Vrms = √3 V
    const s = {
      waveform: "square" as const,
      frequency: 1000,
      rms: Math.sqrt(3),
      offset: 1,
      duty: 25,
    };
    const square = configureSource(source, s);
    expect(Number(square.params.width) + Number(square.params.rise)).toBeCloseTo(0.00025, 12);
    expect(Number(square.params.v1)).toBeCloseTo(-1, 12);
    expect(Number(square.params.v2)).toBeCloseTo(3, 12);
    const triangle = configureSource({ ...source, kind: "idc" }, { ...s, waveform: "triangle" });
    expect(triangle.kind).toBe("ipulse");
    expect(triangle.params.width).toBe("0");
    expect(Number(triangle.params.rise)).toBeCloseTo(0.00025, 12);
    expect(Number(triangle.params.fall)).toBeCloseTo(0.00075, 12);
    expect(sourceSettings(triangle).waveform).toBe("triangle");
    expect(() => configureSource(source, { ...s, duty: 100 })).toThrow();
    expect(() => configureSource(source, { ...s, frequency: 0 })).toThrow();
  });
  it("reads circuits saved with the peak-to-peak field as RMS", () => {
    const legacy = {
      ...source,
      kind: "vsin",
      params: { bench_vpp: "360", freq: "60", amplitude: "180" },
    };
    expect(sourceSettings(legacy).rms).toBeCloseTo(127.279, 3);
    const again = configureSource(legacy, sourceSettings(legacy));
    expect(Number(again.params.amplitude)).toBeCloseTo(180, 3);
    expect(again.params.bench_vpp).toBeUndefined();
    expect(
      sourceSettings({ ...source, kind: "vsin", params: { amplitude: "10" } }).rms,
    ).toBeCloseTo(7.07107, 5);
    expect(peakToPeakFromRms("triangle", 1)).toBeCloseTo(2 * Math.sqrt(3), 12);
    expect(rmsFromPeakToPeak("square", 2)).toBeCloseTo(1, 12);
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
