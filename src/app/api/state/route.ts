import { store } from "@/lib/server/runtime";

export const dynamic = "force-dynamic";
export function GET() {
  return Response.json(store.snapshot(), { headers: { "Cache-Control": "no-store" } });
}
