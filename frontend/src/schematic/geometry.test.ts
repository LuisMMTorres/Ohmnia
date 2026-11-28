import { describe, expect, it } from "vitest";
import { junctions, nextRef, pinPositions, route, simplify, transform } from "./geometry";
import { emptySchematic, type SymbolDef } from "./types";
import { openPins } from "./editing";

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

const OPAMP: SymbolDef = {
  ...R,
  kind: "opamp",
  prefix: "X",
  pins: [
    { name: "inn", dx: -3, dy: -1 },
    { name: "inp", dx: -3, dy: 1 },
    { name: "out", dx: 3, dy: 0 },
    { name: "vcc", dx: 0, dy: -2 },
    { name: "vee", dx: 0, dy: 2 },
  ],
};

describe("op-amp supply pins", () => {
  const u = {
    id: "u",
    kind: "opamp",
    ref: "U1",
    x: 0,
    y: 0,
    rot: 0 as const,
    mirror: false,
    params: {},
    part_id: null,
  };
  it("a wire crossing V+ in the middle of a segment does not join it (no dot, pin open)", () => {
    const sch = {
      ...emptySchematic(),
      components: [u],
      wires: [{ id: "w", points: [[-3, -2] as [number, number], [3, -2] as [number, number]] }],
    };
    expect(junctions(sch, { opamp: OPAMP })).toEqual([]);
    expect(openPins(sch, { opamp: OPAMP }).map((p) => p.pin)).toContain("vcc");
  });
  it("a wire ending on V+ joins it", () => {
    const sch = {
      ...emptySchematic(),
      components: [u],
      wires: [{ id: "w", points: [[0, -2] as [number, number], [0, -5] as [number, number]] }],
    };
    expect(openPins(sch, { opamp: OPAMP }).map((p) => p.pin)).not.toContain("vcc");
  });
});
