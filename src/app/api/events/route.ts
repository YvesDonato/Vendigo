import { store } from "@/lib/server/runtime";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET(request: Request) {
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
      else send(store.snapshot());
    },
    cancel() { cleanup(); },
  });
  return new Response(stream, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", Connection: "keep-alive", "X-Accel-Buffering": "no" } });
}
