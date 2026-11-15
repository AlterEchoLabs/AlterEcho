export const lat = (value: number) => `${Math.abs(value).toFixed(2)}° ${value < 0 ? "S" : "N"}`;
export const lon = (value: number) => `${Math.abs(value).toFixed(2)}° ${value < 0 ? "W" : "E"}`;
export const coords = (latitude: number, longitude: number) => `${lat(latitude)}, ${lon(longitude)}`;
export const pct = (value: number | null | undefined, digits = 0) => value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
export const date = (value: string | null | undefined) => value ? new Date(value).toISOString().slice(0, 10) : "date not recorded";

export function num(value: number | null | undefined, units = "", digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const text = value.toFixed(digits);
  return units === "°" ? `${text}°` : units ? `${text} ${units}` : text;
}

export function signed(value: number | null | undefined, units = "", digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : value < 0 ? "−" : "±"}${num(Math.abs(value), units, digits)}`;
}

export const kToC = (kelvin: number | null | undefined) => kelvin == null ? null : kelvin - 273.15;
