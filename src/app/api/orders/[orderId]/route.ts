import { store } from "@/lib/server/runtime";
import { errorResponse } from "@/lib/server/http";

export const dynamic = "force-dynamic";
export async function GET(_request: Request, context: { params: Promise<{ orderId: string }> }) {
  try {
    const { orderId } = await context.params;
    return Response.json(store.getOrder(orderId), { headers: { "Cache-Control": "no-store" } });
  } catch (error) { return errorResponse(error); }
}
