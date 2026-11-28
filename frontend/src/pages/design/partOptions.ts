import type { CandidateOut, PartFit } from "../../api";

/** Groups of the part picker, in the order they are shown. */
export const PART_GROUPS: { key: "recomendado" | PartFit; label: string }[] = [
  { key: "recomendado", label: "Recomendados (liberados e dentro das margens)" },
  { key: "atende", label: "Atendem às especificações" },
  { key: "margem_menor", label: "Atendem, com margem menor que a do projeto" },
  { key: "nao_atende", label: "Não atendem às especificações" },
  { key: "sem_dados", label: "Sem dados no datasheet para conferir" },
  { key: "incompativel", label: "Outro tipo da família (não cabe nesta posição)" },
];

export const FIT_LABEL: Record<PartFit, string> = {
  atende: "atende",
  margem_menor: "margem menor",
  nao_atende: "não atende",
  sem_dados: "sem dados",
  incompativel: "incompatível",
};

/** Every option of the family split into the picker groups (empty groups left out). */
export function groupParts(
  options: CandidateOut[],
): { key: string; label: string; parts: CandidateOut[] }[] {
  const groupOf = (o: CandidateOut): string =>
    o.recommended ? "recomendado" : (o.fit ?? "atende");
  return PART_GROUPS.map((g) => ({
    ...g,
    parts: options.filter((o) => groupOf(o) === g.key),
  })).filter((g) => g.parts.length > 0);
}

/** Text of one option: part, maker and what the user must know before locking it. */
export function partLabel(o: CandidateOut): string {
  const notes: string[] = [];
  if (!o.released) notes.push("não revisado");
  if (o.fit && o.fit !== "atende" && o.reason) notes.push(o.reason);
  return `${o.part_number} (${o.manufacturer})${notes.length ? " · " + notes.join(" · ") : ""}`;
}
