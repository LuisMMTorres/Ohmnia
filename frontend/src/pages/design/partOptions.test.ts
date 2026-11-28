import { describe, expect, it } from "vitest";
import type { CandidateOut } from "../../api";
import { groupParts, partLabel } from "./partOptions";

const part = (p: Partial<CandidateOut> & { part_number: string }): CandidateOut => ({
  id: p.part_number,
  manufacturer: "Fab",
  released: true,
  ...p,
});

describe("part picker of a circuit position", () => {
  it("shows the recommended parts first and every other part of the family after", () => {
    const groups = groupParts([
      part({ part_number: "A", recommended: true, fit: "atende" }),
      part({ part_number: "B", fit: "atende", released: false }),
      part({
        part_number: "C",
        fit: "nao_atende",
        reason: "não suporta o esforço calculado: VRRM",
      }),
      part({ part_number: "D", fit: "incompativel", reason: "tipo bjt.pnp" }),
    ]);
    expect(groups.map((g) => g.key)).toEqual([
      "recomendado",
      "atende",
      "nao_atende",
      "incompativel",
    ]);
    expect(groups.flatMap((g) => g.parts.map((p) => p.part_number))).toEqual(["A", "B", "C", "D"]);
  });

  it("tells why a part does not meet the design and whether it was reviewed", () => {
    expect(partLabel(part({ part_number: "A", fit: "atende" }))).toBe("A (Fab)");
    expect(
      partLabel(
        part({
          part_number: "C",
          released: false,
          fit: "sem_dados",
          reason: "datasheet sem VRRM para conferir",
        }),
      ),
    ).toBe("C (Fab) · não revisado · datasheet sem VRRM para conferir");
  });
});
