import { nonnegativeInteger, object, readJson, writeJson } from "./json-file.ts";
import type { Robot, VenueLocation } from "../../types/index.ts";

export interface AnalyticsDocument {
  qr_scans: number;
  visit_ids: string[];
  buyer_ids: string[];
  revision: number;
  started_at: string;
  robots: Robot[];
  locations: VenueLocation[];
}

export function validateAnalytics(value: unknown): asserts value is AnalyticsDocument {
  if (!object(value) || !nonnegativeInteger(value.qr_scans) || !nonnegativeInteger(value.revision) ||
      !Array.isArray(value.visit_ids) || value.visit_ids.some((id) => typeof id !== "string") ||
      !Array.isArray(value.buyer_ids) || value.buyer_ids.some((id) => typeof id !== "string") ||
      typeof value.started_at !== "string" || !Number.isFinite(Date.parse(value.started_at)) ||
      !Array.isArray(value.robots) || !Array.isArray(value.locations)) throw new Error("Invalid analytics.json.");
}

/** Revenue and purchase counts are derived from PurchaseStore, never copied here. */
export class AnalyticsStore {
  readonly path: string;
  constructor(path: string) { this.path = path; }
  read(): AnalyticsDocument { const value = readJson(this.path); validateAnalytics(value); return value; }
  write(value: AnalyticsDocument) { validateAnalytics(value); writeJson(this.path, value); }
}
