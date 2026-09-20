import { getStore } from "@/lib/server/runtime";
import { compartmentField, errorResponse, jsonBody, stringField } from "@/lib/server/http";
import { BlobStore } from "@/lib/server/blob-store";
import { after } from "next/server";

export const maxDuration = 60;

export async function POST(request: Request) {
  try {
    const body = await jsonBody(request);
    const store = getStore();
    const orderId = stringField(body, "orderId");
    // Register before hardware IO, so a lost response or failed acknowledgement
    // still has a server-owned recovery task. No naked serverless setTimeout.
    if (store instanceof BlobStore) after(() => store.finishPickup(orderId));
    const order = await store.purchase({ orderId, robotId: stringField(body, "robotId"), productId: stringField(body, "productId"), sessionId: stringField(body, "sessionId"), compartmentId: compartmentField(body) });
    return Response.json(order, { status: order.status === "failed" ? 502 : 200 });
  } catch (error) { return errorResponse(error); }
}
