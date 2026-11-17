import { expect, it } from "vitest";
import { scopePoints } from "./scopeGeometry";
it("shows 2.5 V operating point as a horizontal DC level without requiring time samples", () => {
  expect(scopePoints([], [2.5], 1, 0, false, 0, 0.001, true)).toEqual([
    { x: 70, y: 92.5 },
    { x: 950, y: 92.5 },
  ]);
  expect(scopePoints([], [2.5], 1, 0, true, 0, 0.001, true)).toEqual([
    { x: 70, y: 205 },
    { x: 950, y: 205 },
  ]);
  expect(scopePoints([], [], 1, 0, false, 0, 0.001, true)).toEqual([]);
});
it("retains a constant transient and a time-varying transient", () => {
  expect(scopePoints([0, 0.01], [5, 5], 2, 0, false, 0, 0.001, false)).toEqual([
    { x: 70, y: 92.5 },
    { x: 950, y: 92.5 },
  ]);
  expect(scopePoints([0, 0.01], [0, 1], 1, 0, false, 0, 0.001, false)).toEqual([
    { x: 70, y: 205 },
    { x: 950, y: 160 },
  ]);
});
