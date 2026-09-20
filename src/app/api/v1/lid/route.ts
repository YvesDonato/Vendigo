import { timingSafeEqual } from "node:crypto";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function reply(body: object, status = 200) {
  return Response.json(body, { status, headers: { "Cache-Control": "no-store" } });
}

async function handle(request: Request, write: boolean) {
  let apiToken: string;
  try {
    // Credentials are provisioned on the host, never bundled into build artifacts.
    apiToken = (await readFile(/* turbopackIgnore: true */ process.env.LID_API_TOKEN_FILE ?? join(process.cwd(), "robot_code/lid-api.token"), "utf8")).trim();
    if (apiToken.length < 32) throw new Error("Missing API token");
  } catch {
    return reply({ error: "Lid API is not configured." }, 503);
  }
  const supplied = Buffer.from(request.headers.get("Authorization") ?? "");
  const expected = Buffer.from(`Bearer ${apiToken}`);
  if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) {
    return reply({ error: "Unauthorized." }, 401);
  }

  let angle: number | undefined;
  if (write) {
    if (request.headers.get("Content-Type")?.split(";")[0].trim() !== "application/json") {
      return reply({ error: "Send application/json with state: open or closed." }, 415);
    }
    try {
      const body: unknown = await request.json();
      if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).length !== 1 || !("state" in body)) throw new Error();
      if (body.state !== "open" && body.state !== "closed") throw new Error();
      angle = body.state === "open" ? 0 : 180;
    } catch {
      return reply({ error: "Send exactly {\"state\":\"open\"} or {\"state\":\"closed\"}." }, 400);
    }
  }

  let controllerToken: string;
  let url: URL;
  try {
    controllerToken = (await readFile(/* turbopackIgnore: true */ process.env.LID_CONTROLLER_TOKEN_FILE ?? join(process.cwd(), "robot_code/control.token"), "utf8")).trim();
    if (!controllerToken) throw new Error();
    url = new URL(write ? "/servo" : "/status", process.env.LID_CONTROLLER_URL ?? "http://192.168.8.100");
    if (!["http:", "https:"].includes(url.protocol)) throw new Error();
  } catch {
    return reply({ error: "Lid controller is not configured." }, 503);
  }
  try {
    const response = await fetch(url, {
      method: write ? "POST" : "GET",
      headers: { Authorization: `Bearer ${controllerToken}` },
      body: write ? new URLSearchParams({ angle: String(angle) }) : undefined,
      cache: "no-store", redirect: "error", signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) return reply({ error: "Lid controller rejected the request." }, 502);
    const state = await response.json();
    if (typeof state.servo_enabled !== "boolean" || !(state.servo_angle === null || (Number.isInteger(state.servo_angle) && state.servo_angle >= 0 && state.servo_angle <= 180))) throw new Error();
    if (write && (state.ok !== true || state.servo_angle !== angle)) throw new Error();
    return reply({
      commanded_state: state.servo_angle === 0 ? "open" : state.servo_angle === 180 ? "closed" : "unknown",
      commanded_angle: state.servo_angle,
      enabled: state.servo_enabled,
      position_feedback: false,
    });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return reply({ error: timedOut ? "Lid controller timed out." : "Lid controller is unavailable." }, timedOut ? 504 : 502);
  }
}

export async function GET(request: Request) { return handle(request, false); }
export async function POST(request: Request) { return handle(request, true); }
