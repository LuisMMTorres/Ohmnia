import { describe, expect, it } from "vitest";
import { glowFrom } from "./indicators";

describe("glowFrom", () => {
  it("LED at its reference current shines 100 %", () => {
    const g = glowFrom(
      { kind: "led", vector: "i(vlum_led1)", i_ref: 0.02, i_max: 0.03, colour: "verde" },
      [0, 0.02, 0.02, 0.02, 0.02, 0.02],
    )!;
    expect(g.level).toBeCloseTo(1);
    expect(g.burnt).toBe(false);
  });
  it("LED above the maximum DC current burns", () => {
    const g = glowFrom({ kind: "led", vector: "x", i_ref: 0.02, i_max: 0.03 }, [0.05])!;
    expect(g.burnt).toBe(true);
  });
  it("LED in reverse does not shine", () => {
    const g = glowFrom({ kind: "led", vector: "x", i_ref: 0.02, i_max: 0.03 }, [-1e-6])!;
    expect(g.level).toBe(0);
  });
  it("lamp on its rated RMS voltage gives the rated power", () => {
    // 12 V 21 W: R = 144/21; sine of 12 V RMS
    const r = 144 / 21;
    const v = Array.from(
      { length: 2000 },
      (_, k) => Math.sqrt(2) * 12 * Math.sin((2 * Math.PI * k) / 100),
    );
    const g = glowFrom(
      { kind: "lamp", vector: "x", r, p_nom: 21 },
      v.map((x) => x / r),
    )!;
    expect(g.level).toBeCloseTo(1, 2);
    expect(g.burnt).toBe(false);
  });
});
