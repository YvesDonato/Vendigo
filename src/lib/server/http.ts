import { AppError } from "./store";

export async function jsonBody(request: Request): Promise<Record<string, unknown>> {
  try {
    const value: unknown = await request.json();
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error();
    return value as Record<string, unknown>;
  } catch {
    throw new AppError("Please send a valid JSON object.");
  }
}

export function stringField(body: Record<string, unknown>, field: string) {
  const value = body[field];
  if (typeof value !== "string" || !/^[a-zA-Z0-9_-]{1,100}$/.test(value)) throw new AppError(`Invalid ${field}.`);
  return value;
}

export function compartmentField(body: Record<string, unknown>) {
  if (typeof body.compartmentId !== "number" || !Number.isInteger(body.compartmentId) || body.compartmentId < 1) throw new AppError("Invalid compartmentId.");
  return body.compartmentId;
}

export function errorResponse(error: unknown) {
  if (error instanceof AppError) return Response.json({ error: error.message }, { status: error.status });
  console.error("Vendigo request failed:", error);
  return Response.json({ error: "Vendigo couldn’t complete that request. Please try again." }, { status: 500 });
}
