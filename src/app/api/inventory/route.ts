import { getStore } from "@/lib/server/runtime";
import { AppError } from "@/lib/server/store";
import { errorResponse, jsonBody, stringField } from "@/lib/server/http";

export async function POST(request: Request) {
  try {
    const body = await jsonBody(request);
    if (!Array.isArray(body.items)) throw new AppError("Send inventory quantities.");
    return Response.json(getStore().setInventory(stringField(body, "robotId"), body.items));
  } catch (error) { return errorResponse(error); }
}
