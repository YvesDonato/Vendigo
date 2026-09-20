import { getStore } from "@/lib/server/runtime";
import { compartmentField, errorResponse, jsonBody, stringField } from "@/lib/server/http";

export async function POST(request: Request) {
  try {
    const body = await jsonBody(request);
    const order = await getStore().purchase({ orderId: stringField(body, "orderId"), robotId: stringField(body, "robotId"), productId: stringField(body, "productId"), sessionId: stringField(body, "sessionId"), compartmentId: compartmentField(body) });
    return Response.json(order, { status: order.status === "failed" ? 502 : 200 });
  } catch (error) { return errorResponse(error); }
}
