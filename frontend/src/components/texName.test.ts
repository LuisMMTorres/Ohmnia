import { describe, expect, it } from "vitest";
import { texName } from "./CalcSteps";

describe("texName", () => {
  it("braces multi-character subscripts only", () => {
    expect(texName("E_on")).toBe("E_{on}");
    expect(texName("V_pk,max")).toBe("V_{pk,max}");
    expect(texName("I_O+")).toBe("I_{O+}");
    expect(texName("V_s")).toBe("V_s");
    expect(texName("R_{DS(on)}")).toBe("R_{DS(on)}");
    expect(texName("α")).toBe("α");
  });
});
