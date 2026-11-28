import { describe, expect, it } from "vitest";
import { holeXY } from "./geometry";
import type { BoardSpec, Breadboard } from "./types";
import { moveLead, moveWire, moveWireEnd, occupiedExcept, removeWire } from "./wireEdit";

const RAIL_ROWS = Array.from({ length: 10 }, (_, g) =>
  [2, 3, 4, 5, 6].map((r) => r + 6 * g),
).flat();
const board: BoardSpec = {
  id: "830",
  label: "",
  rows: 63,
  upper: "abcde",
  lower: "fghij",
  rails: ["tp", "tn", "bn", "bp"],
  rail_rows: RAIL_ROWS,
  split_after: 30,
  y: {
    tp: 0,
    tn: 1,
    a: 3,
    b: 4,
    c: 5,
    d: 6,
    e: 7,
    f: 10,
    g: 11,
    h: 12,
    i: 13,
    j: 14,
    bn: 16,
    bp: 17,
  },
  rail_polarity: { tp: "+", tn: "-", bn: "-", bp: "+" },
};
const bb = (): Breadboard => ({
  board: "830",
  rails_split: false,
  parts: [
    { ref: "R1", package: "axial", legs: { "1": "a10", "2": "a14" } },
    { ref: "V1", package: "bench", legs: { p: "tp2", n: "tn2" } },
  ],
  wires: [
    { id: "w1", a: "c10", b: "c20", color: "verde" },
    { id: "w2", a: "e30", b: "f30", color: "azul" },
  ],
});

describe("editing wires on the breadboard", () => {
  it("moves one end of a wire to a free hole and keeps the other", () => {
    expect(moveWireEnd(bb(), "w1", "b", "d25")).toMatchObject({ a: "c10", b: "d25" });
  });

  it("refuses a hole already taken by a leg, a lead or another wire", () => {
    expect(moveWireEnd(bb(), "w1", "b", "a14")).toBeNull();
    expect(moveWireEnd(bb(), "w1", "b", "tp2")).toBeNull();
    expect(moveWireEnd(bb(), "w1", "b", "f30")).toBeNull();
    // nor both ends in the same hole
    expect(moveWireEnd(bb(), "w1", "b", "c10")).toBeNull();
  });

  it("drags the whole wire by whole holes, keeping its shape", () => {
    const [x0, y0] = holeXY(board, "c10");
    const [x1, y1] = holeXY(board, "d13");
    expect(moveWire(board, bb(), "w1", x1 - x0 + 2, y1 - y0 - 3)).toMatchObject({
      a: "d13",
      b: "d23",
    });
    // carried onto the second board too
    const [x2, y2] = holeXY(board, "2:c10");
    expect(moveWire(board, bb(), "w1", x2 - x0, y2 - y0)).toMatchObject({
      a: "2:c10",
      b: "2:c20",
    });
  });

  it("does not drop a dragged wire on taken holes or off the board", () => {
    const [x0] = holeXY(board, "c10");
    const [x1] = holeXY(board, "c30");
    // 20 holes to the right: c30 and c40 are free
    expect(moveWire(board, bb(), "w1", x1 - x0, 0)).toMatchObject({ a: "c30", b: "c40" });
    const [, ya] = holeXY(board, "c10");
    const [, ye] = holeXY(board, "e10");
    // and two rows down as well, end a would land on e30, taken by w2
    expect(moveWire(board, bb(), "w1", x1 - x0, ye - ya)).toBeNull();
    expect(moveWire(board, bb(), "w1", 5000, 0)).toBeNull();
  });

  it("clips an instrument lead to another hole and unclips it", () => {
    const moved = moveLead(bb(), "V1", "n", "bn2");
    expect(moved?.parts.find((p) => p.ref === "V1")?.legs).toEqual({ p: "tp2", n: "bn2" });
    expect(moveLead(bb(), "V1", "n", "a10")).toBeNull();
    const out = removeWire(bb(), { kind: "lead", ref: "V1", terminal: "n" });
    expect(out.parts.find((p) => p.ref === "V1")?.legs).toEqual({ p: "tp2" });
  });

  it("deletes the selected wire only", () => {
    expect(removeWire(bb(), { kind: "wire", id: "w1" }).wires.map((w) => w.id)).toEqual(["w2"]);
    expect(occupiedExcept(bb(), { kind: "wire", id: "w1" }).has("c10")).toBe(false);
  });
});
