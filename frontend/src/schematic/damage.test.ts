import { describe, expect, it } from "vitest";
import type { DamageOut } from "../api";
import { damageByRef } from "./damage";

const d = (ref: string, name: string, reviewed = true): DamageOut => ({
  ref,
  quantity: "I",
  name,
  value: 0.4,
  limit: 0.15,
  unit: "A",
  cause: `${ref}: ${name} excedida.`,
  advice: "Reduza a corrente.",
  source: `fonte ${name}`,
  reviewed,
});

describe("damageByRef", () => {
  it("groups the ratings of a part and keeps the schematic order", () => {
    const out = damageByRef(
      [d("D2", "IF(AV)"), d("D1", "IF(AV)"), d("D1", "Ptot", false)],
      {},
      () => null,
      ["D1", "D2"],
    );
    expect(out.map((p) => p.ref)).toEqual(["D1", "D2"]);
    expect(out[0]!.causes).toHaveLength(2);
    expect(out[0]!.advice).toEqual(["Reduza a corrente."]);
    expect(out[0]!.unreviewed).toBe(true);
    expect(out[1]!.unreviewed).toBe(false);
  });

  it("adds LEDs the brightness calculation marks as burnt", () => {
    const out = damageByRef(
      [],
      { LED1: { level: 3, color: "red", burnt: true }, LED2: { level: 1, color: "red" } },
      (ref) => `${ref}: acima de IF máx.`,
      ["LED1", "LED2"],
    );
    expect(out.map((p) => p.ref)).toEqual(["LED1"]);
    expect(out[0]!.causes[0]).toContain("IF máx");
    expect(out[0]!.advice[0]).toContain("resistor em série");
  });
});
