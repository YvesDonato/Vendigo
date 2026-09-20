import { getStore } from "@/lib/server/runtime";
import { errorResponse } from "@/lib/server/http";

export const dynamic = "force-dynamic";
export async function GET() {
  try { return Response.json(await getStore().snapshot(), { headers: { "Cache-Control": "no-store" } }); }
  catch (error) { return errorResponse(error); }
}
