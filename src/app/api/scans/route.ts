import { store } from "@/lib/server/runtime";
import { errorResponse, jsonBody, stringField } from "@/lib/server/http";

export async function POST(request: Request) {
  try {
    const body = await jsonBody(request);
    store.scan(stringField(body, "robotId"), stringField(body, "sessionId"));
    return Response.json({ ok: true });
  } catch (error) { return errorResponse(error); }
}
