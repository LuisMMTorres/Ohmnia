import { describe, expect, it } from "vitest";
import { fitScale } from "./benchScale";

const mk = (label: string, v: number, i: number) => ({
  label,
  v: { value: v, unit: "V" },
  i: { value: i, unit: "A" },
});

describe("fitScale", () => {
  it("follows the model curves and lists far-away datasheet points", () => {
    const s = fitScale([[0, 1e-3, 2e-3]], [mk("near", 1, 2.5e-3), mk("far", 1, 1)], 10, false);
    expect(s.range[1]).toBeLessThan(0.01);
    expect(s.inside.map((m) => m.label)).toEqual(["near"]);
    expect(s.outside[0]).toContain("far");
  });
  it("drops points beyond the x range", () => {
    const s = fitScale([[0, 1]], [mk("x", 20, 0.5)], 10, false);
    expect(s.inside).toHaveLength(0);
    expect(s.outside).toHaveLength(1);
  });
});
