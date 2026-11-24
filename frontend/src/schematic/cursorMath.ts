/** Measurements use signal units, independent of display gain and vertical position. */
export function sampleAt(
  times: number[],
  values: number[],
  time: number,
  operatingPoint: boolean,
  ac: boolean,
  mean?: number,
): number | null {
  if (!values.length || !Number.isFinite(time)) return null;
  let result: number;
  if (operatingPoint) result = values[0]!;
  else {
    if (!times.length || time < times[0]! || time > times[times.length - 1]!) return null;
    let lo = 0,
      hi = times.length - 1;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (times[mid]! < time) lo = mid + 1;
      else hi = mid;
    }
    if (times[lo] === time) result = values[lo]!;
    else {
      const a = lo - 1,
        span = times[lo]! - times[a]!;
      if (a < 0 || span <= 0 || values[a] == null || values[lo] == null) return null;
      result = values[a]! + ((values[lo]! - values[a]!) * (time - times[a]!)) / span;
    }
  }
  if (ac) result -= mean ?? values.reduce((sum, value) => sum + value, 0) / values.length;
  return Number.isFinite(result) ? result : null;
}

export const amplitudeY = (value: number, scale: number, position: number) =>
  205 - (value / scale + position) * 45;
export const amplitudeAtY = (y: number, scale: number, position: number) =>
  ((205 - y) / 45 - position) * scale;

export function cursorDelta(a: number | null, b: number | null): number | null {
  return a == null || b == null ? null : b - a;
}
