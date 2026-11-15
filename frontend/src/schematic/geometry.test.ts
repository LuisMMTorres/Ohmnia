import { describe, expect, it } from "vitest";
import { junctions, nextRef, pinPositions, route, simplify, transform } from "./geometry";
import { emptySchematic, type SymbolDef } from "./types";

const R: SymbolDef = {
  kind: "resistor",
  label: "R",
  group: "",
  prefix: "R",
  pins: [
    { name: "1", dx: -2, dy: 0 },
    { name: "2", dx: 2, dy: 0 },
  ],
  params: [],
  catalogue: [],
  tolerance: null,
  description: "",
};

describe("geometry", () => {
  it("rotates like the backend", () => {
    expect(transform(2, 0, 90, false)).toEqual([0, 2]);
    expect(transform(2, 0, 180, false)).toEqual([-2, 0]);
    expect(transform(2, 1, 90, true)).toEqual([-1, -2]);
  });
  it("places pins", () => {
    const c = {
      id: "1",
      kind: "resistor",
      ref: "R1",
      x: 5,
      y: 5,
      rot: 90 as const,
      mirror: false,
      params: {},
      part_id: null,
    };
    expect(pinPositions(c, R)).toEqual({ "1": [5, 3], "2": [5, 7] });
  });
  it("routes and simplifies", () => {
    expect(route([0, 0], [3, 4])).toEqual([
      [0, 0],
      [3, 0],
      [3, 4],
    ]);
    expect(route([0, 0], [3, 4], true)).toEqual([
      [0, 0],
      [0, 4],
      [3, 4],
    ]);
    expect(
      simplify([
        [0, 0],
        [1, 0],
        [2, 0],
        [2, 0],
        [2, 3],
      ]),
    ).toEqual([
      [0, 0],
      [2, 0],
      [2, 3],
    ]);
  });
  it("finds T junctions but not crossings", () => {
    const sch = emptySchematic();
    sch.wires = [
      {
        id: "a",
        points: [
          [0, 0],
          [10, 0],
        ],
      },
      {
        id: "b",
        points: [
          [5, 0],
          [5, 5],
        ],
      }, // T
      {
        id: "c",
        points: [
          [8, -3],
          [8, 3],
        ],
      }, // crossing, no dot
    ];
    expect(junctions(sch, { resistor: R })).toEqual([[5, 0]]);
  });
  it("numbers designators", () => {
    const sch = emptySchematic();
    sch.components = [
      {
        id: "1",
        kind: "resistor",
        ref: "R1",
        x: 0,
        y: 0,
        rot: 0,
        mirror: false,
        params: {},
        part_id: null,
      },
    ];
    expect(nextRef(sch, "R")).toBe("R2");
  });
});
