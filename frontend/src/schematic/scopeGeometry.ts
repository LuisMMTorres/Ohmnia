/** A scalar operating point is displayed as a DC level, not as acquired time samples. */
export function scopePoints(
  times: number[],
  values: number[],
  scale: number,
  position: number,
  ac: boolean,
  start: number,
  timeDiv: number,
  operatingPoint: boolean,
): { x: number; y: number }[] {
  if (!values.length) return [];
  const mean = ac ? values.reduce((a, b) => a + b, 0) / values.length : 0;
  const y = (v: number) => 205 - ((v - mean) / scale + position) * 45;
  if (operatingPoint)
    return Number.isFinite(values[0])
      ? [
          { x: 70, y: y(values[0]!) },
          { x: 950, y: y(values[0]!) },
        ]
      : [];
  return times
    .map((t, i) => ({ x: 70 + ((t - start) / timeDiv) * 88, y: y(values[i]!) }))
    .filter((p) => p.x >= -100 && p.x <= 1100 && Number.isFinite(p.y));
}
