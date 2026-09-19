import type { ToolEvent } from "@/agent/run-agent";

export function ToolActivity({ event }: { event: ToolEvent }) {
  const completed = event.status === "completed";

  return (
    <div className="my-2 overflow-hidden rounded-2xl border border-sky-100 bg-sky-50/60 text-sm">
      <div className="flex items-center gap-2 border-b border-sky-50 px-3.5 py-2.5 font-medium text-slate-800">
        <span className="flex size-6 items-center justify-center rounded-full bg-sky-500 text-xs text-white">↗</span>
        Car
        <span className="ml-auto text-xs font-normal text-slate-400">Simulated</span>
      </div>
      <div className="px-3.5 py-3">
        <div className="text-slate-700">
          {event.source ?? "Unknown source"} <span className="px-1 text-sky-300">→</span>{" "}
          {event.target ?? "Unknown target"}
        </div>
        <div className={`mt-1.5 text-xs font-medium ${completed ? "text-sky-700" : "text-red-700"}`}>
          {completed ? "Arrived" : "Task failed"}
        </div>
      </div>
    </div>
  );
}
