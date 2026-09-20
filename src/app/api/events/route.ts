import { getStore } from "@/lib/server/runtime";
import { errorResponse } from "@/lib/server/http";
import { BlobStore } from "@/lib/server/blob-store";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET(request: Request) {
  let store;
  let initial;
  try {
    const backend = getStore();
    // SSE subscribers in different Vercel instances cannot share a process.
    // 204 tells EventSource to stop reconnecting; the existing live poll remains.
    if (backend instanceof BlobStore) return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
    store = backend; initial = store.snapshot();
  }
  catch (error) { return errorResponse(error); }
  const encoder = new TextEncoder();
  let cleanup = () => {};
  const stream = new ReadableStream({
    start(controller) {
      let closed = false;
      const send = (snapshot: ReturnType<typeof store.snapshot>) => {
        if (!closed) controller.enqueue(encoder.encode(`data: ${JSON.stringify(snapshot)}\n\n`));
      };
      const unsubscribe = store.subscribe(send);
      const heartbeat = setInterval(() => {
        if (!closed) controller.enqueue(encoder.encode(": heartbeat\n\n"));
      }, 15_000);
      cleanup = () => {
        if (closed) return;
        closed = true;
        clearInterval(heartbeat);
        unsubscribe();
        request.signal.removeEventListener("abort", abort);
      };
      const abort = () => { cleanup(); controller.close(); };
      request.signal.addEventListener("abort", abort, { once: true });
      if (request.signal.aborted) abort();
      else send(initial);
    },
    cancel() { cleanup(); },
  });
  return new Response(stream, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", Connection: "keep-alive", "X-Accel-Buffering": "no" } });
}
