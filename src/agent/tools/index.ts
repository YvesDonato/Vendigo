import type { FunctionTool } from "openai/resources/responses/responses";
import { carNavigate, type CarNavigateInput } from "./car-navigate.ts";
import { resolveLocation, type ResolveLocationInput } from "./resolve-location.ts";

export const agentTools: FunctionTool[] = [
  {
    type: "function",
    name: "resolve_location",
    description: "Resolve a venue place name, alias, or room number using the venue registry. Returns candidates when ambiguous.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Location name, alias, or room number." },
        floor: { type: "number", description: "Floor number, when the user provided one." },
      },
      required: ["query"],
      additionalProperties: false,
    },
    strict: false,
  },
  {
    type: "function",
    name: "car_navigate",
    description: "Navigate the simulated car between two already-resolved venue location IDs.",
    parameters: {
      type: "object",
      properties: {
        source_location_id: { type: "string" },
        target_location_id: { type: "string" },
      },
      required: ["source_location_id", "target_location_id"],
      additionalProperties: false,
    },
    strict: true,
  },
];

export async function executeTool(name: string, rawArguments: string) {
  const args: unknown = JSON.parse(rawArguments);
  if (!args || typeof args !== "object" || Array.isArray(args)) {
    throw new Error("Tool arguments must be an object.");
  }

  const values = args as Record<string, unknown>;

  if (name === "resolve_location") {
    if (typeof values.query !== "string") {
      throw new Error("resolve_location requires a query.");
    }
    if (values.floor !== undefined && typeof values.floor !== "number") {
      throw new Error("resolve_location floor must be a number.");
    }
    return resolveLocation(values as ResolveLocationInput);
  }

  if (name === "car_navigate") {
    if (
      typeof values.source_location_id !== "string" ||
      typeof values.target_location_id !== "string"
    ) {
      throw new Error("car_navigate requires source and target location IDs.");
    }
    return carNavigate(values as CarNavigateInput);
  }

  throw new Error(`Unknown tool: ${name}`);
}
