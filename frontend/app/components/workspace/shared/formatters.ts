import type { SourceManifest } from "../../../../lib/api";

export const label = (value: string) => value.replaceAll("_", " ");

export const dataLabel = (value: string) => ({
  real_processed: "Real processed",
  demo_fixture: "Demo preview",
  metadata_only: "Metadata only",
  unavailable: "Unavailable",
}[value] ?? label(value));

export const coordinate = (value: number) => `${Math.abs(value).toFixed(3)}° ${value < 0 ? "S" : "N"}`;

export const longitude = (value: number) => `${Math.abs(value).toFixed(3)}° ${value < 0 ? "W" : "E"}`;

export const resolutionLabel = (resolution: SourceManifest["native_resolution"]) =>
  Array.isArray(resolution) ? resolution.map((value) => Number(value).toPrecision(3)).join(" × ") : resolution ?? "Not reported";
