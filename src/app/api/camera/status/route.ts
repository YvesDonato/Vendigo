import { cameraStreamUrl } from "@/lib/camera/config";

export const dynamic = "force-dynamic";
export function GET() {
  return Response.json({ configured: Boolean(cameraStreamUrl()) });
}
