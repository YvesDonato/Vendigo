import { cameraStreamUrl } from "@/lib/camera/config";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request) {
  const url = cameraStreamUrl();
  if (!url) return Response.json({ error: "The robot camera is not connected." }, { status: 503 });
  const abort = new AbortController();
  const disconnect = () => abort.abort();
  request.signal.addEventListener("abort", disconnect, { once: true });
  // The timeout applies to receiving headers, not the lifetime of the MJPEG feed.
  const timeout = setTimeout(() => abort.abort(), 5_000);
  try {
    const response = await fetch(url, { signal: abort.signal, cache: "no-store" });
    clearTimeout(timeout);
    const contentType = response.headers.get("content-type") ?? "";
    if (!response.ok || !response.body || !contentType.includes("multipart/x-mixed-replace")) throw new Error("Camera stream unavailable");
    const reader = response.body.getReader();
    const cleanup = () => request.signal.removeEventListener("abort", disconnect);
    const stream = new ReadableStream({
      async pull(controller) {
        try {
          const { value, done } = await reader.read();
          if (done) { cleanup(); controller.close(); }
          else controller.enqueue(value);
        } catch (error) { cleanup(); controller.error(error); }
      },
      async cancel() { cleanup(); abort.abort(); await reader.cancel().catch(() => {}); },
    });
    return new Response(stream, { headers: { "Content-Type": contentType, "Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no" } });
  } catch {
    clearTimeout(timeout);
    request.signal.removeEventListener("abort", disconnect);
    abort.abort();
    return Response.json({ error: "The robot camera is offline. Check its power and Wi-Fi." }, { status: 502 });
  }
}
