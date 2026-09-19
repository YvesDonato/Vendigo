import { store } from "@/lib/server/runtime";
import { AppError } from "@/lib/server/store";
import { compartmentField, errorResponse, jsonBody, stringField } from "@/lib/server/http";
import type { RobotCommand } from "@/types";

export async function POST(request: Request) {
  try {
    const body = await jsonBody(request);
    const command = stringField(body, "command") as RobotCommand;
    if (!["stop", "resume", "return-to-base", "unlock", "retry-lock"].includes(command)) throw new AppError("Unknown robot command.");
    const order = await store.command(stringField(body, "robotId"), command, command === "unlock" ? compartmentField(body) : undefined);
    if (order?.status === "failed") throw new AppError(order.error!, 502);
    return Response.json({ ok: true, order });
  } catch (error) { return errorResponse(error); }
}
