import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { randomUUID } from "node:crypto";

/** All file IO for retail storage stays behind this boundary. */
export function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

export function writeJson(path: string, value: unknown) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${randomUUID()}.tmp`;
  try {
    const fd = openSync(temporary, "wx", 0o600);
    try {
      writeFileSync(fd, JSON.stringify(value, null, 2) + "\n");
      fsyncSync(fd);
    } finally { closeSync(fd); }
    renameSync(temporary, path);
  } finally {
    if (existsSync(temporary)) unlinkSync(temporary);
  }
}

export function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function nonnegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

export function moneyCents(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 ||
      !Number.isSafeInteger(Math.round(value * 100)) || Math.abs(value * 100 - Math.round(value * 100)) > 0.000001) {
    throw new Error("Prices must be nonnegative amounts with at most two decimal places.");
  }
  return Math.round(value * 100);
}
