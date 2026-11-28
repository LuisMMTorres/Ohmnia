import type { CandidateOut } from "../../api";
import { FIT_LABEL, groupParts, partLabel } from "./partOptions";

/**
 * Picker of the catalogue part of one circuit position: every part of the family, the
 * recommended ones first, the others grouped by how they meet the calculated stresses.
 * Parts of another type (other polarity, other device) are shown but cannot be chosen.
 */
export function PartSelect({
  options,
  value,
  onChange,
  autoLabel = "automático",
  ariaLabel,
}: {
  options: CandidateOut[];
  value: string;
  onChange: (id: string) => void;
  autoLabel?: string;
  ariaLabel?: string;
}) {
  const groups = groupParts(options);
  const chosen = options.find((o) => o.id === value);
  const usable = options.filter((o) => o.fit !== "incompativel").length;
  return (
    <span className="part-select">
      <select aria-label={ariaLabel} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{autoLabel}</option>
        {groups.map((g) => (
          <optgroup key={g.key} label={`${g.label} (${g.parts.length})`}>
            {g.parts.map((o) => (
              <option key={o.id} value={o.id} disabled={o.fit === "incompativel"}>
                {partLabel(o)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <span className="muted small part-count">{usable} opções da família no catálogo</span>
      {chosen && chosen.fit && chosen.fit !== "atende" && (
        <span className={`badge fit-${chosen.fit}`} title={chosen.reason ?? undefined}>
          {FIT_LABEL[chosen.fit]}
        </span>
      )}
    </span>
  );
}
