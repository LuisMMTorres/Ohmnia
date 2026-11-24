import { describe, expect, it } from "vitest";
import { amplitudeAtY, amplitudeY, cursorDelta, sampleAt } from "./cursorMath";

describe("oscilloscope measurements", () => {
  it("interpolates adaptive time steps and keeps negative B-A deltas", () => {
    const t = [0, 0.001, 0.004];
    expect(sampleAt(t, [0, 2, 8], 0.0025, false, false)).toBeCloseTo(5);
    expect(sampleAt(t, [0, 2, 8], 0.001, false, false)).toBe(2);
    expect(cursorDelta(0.004, 0.001)).toBeCloseTo(-0.003);
    expect(cursorDelta(2.5, -1.5)).toBe(-4);
    expect(cursorDelta(null, 2)).toBeNull();
  });
  it("does not extrapolate beyond acquisition or fill missing values", () => {
    expect(sampleAt([1, 2], [4, 8], 0, false, false)).toBeNull();
    expect(sampleAt([1, 2], [4, 8], 3, false, false)).toBeNull();
    expect(sampleAt([], [], 0, false, false)).toBeNull();
    expect(sampleAt([0, 1], [0, NaN], 0.5, false, false)).toBeNull();
    expect(sampleAt([1], [4], 1, false, false)).toBe(4);
  });
  it("measures displayed AC levels and constant operating points without inventing time", () => {
    expect(sampleAt([0, 1], [2, 4], 0.5, false, true)).toBe(0);
    expect(sampleAt([], [2.5], 0, true, false)).toBe(2.5);
    expect(sampleAt([], [2.5], 0, true, true)).toBe(0);
  });
  it("converts horizontal cursors with gain and position without altering signal amplitudes", () => {
    for (const value of [-2.5, 0, 7.5]) {
      expect(amplitudeAtY(amplitudeY(value, 2, -1.5), 2, -1.5)).toBeCloseTo(value);
    }
  });
});
