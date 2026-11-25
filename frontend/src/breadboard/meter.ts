/** Time-weighted readings on the adaptive transient grid; AC removes the DC component. */
export function meterReadings(times: number[], values: number[]) {
  if (!values.length || times.length !== values.length) return null;
  let integral = 0,
    square = 0;
  const duration = times.at(-1)! - times[0]!;
  for (let i = 1; i < times.length; i++) {
    const dt = times[i]! - times[i - 1]!;
    integral += (dt * (values[i]! + values[i - 1]!)) / 2;
    square += (dt * (values[i]! ** 2 + values[i - 1]! ** 2)) / 2;
  }
  const mean = duration > 0 ? integral / duration : values.at(-1)!;
  const meanSquare = duration > 0 ? square / duration : mean ** 2;
  return {
    duration,
    instant: values.at(-1)!,
    mean,
    rms: Math.sqrt(Math.max(0, meanSquare)),
    acRms: Math.sqrt(Math.max(0, meanSquare - mean ** 2)),
  };
}
