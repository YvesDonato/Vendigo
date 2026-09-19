import type { ToolEvent } from "@/agent/run-agent";
import { ToolActivity } from "./ToolActivity";

export type UIMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  events?: ToolEvent[];
};

export function Message({ message }: { message: UIMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`chat-bubble max-w-[88%] px-4 py-2.5 ${
          isUser
            ? "chat-bubble-user rounded-3xl rounded-br-lg text-white"
            : "chat-bubble-agent rounded-3xl rounded-bl-lg text-slate-800"
        }`}
      >
        {!isUser && <div className="mb-1.5 text-xs font-semibold tracking-wide text-sky-600">Claw-Mobile</div>}
        {message.events?.map((event, index) => (
          <ToolActivity event={event} key={`${message.id}-${index}`} />
        ))}
        <p className="whitespace-pre-wrap text-[15px] leading-6">{message.content}</p>
      </div>
    </div>
  );
}
