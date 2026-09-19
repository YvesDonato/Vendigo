"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import type { AgentResult } from "@/agent/run-agent";
import { Message, type UIMessage } from "./Message";
import { VoiceControl } from "./VoiceControl";

const initialMessage: UIMessage = {
  id: "welcome",
  role: "assistant",
  content: "Where are you, and what should I do?",
};

export function Chat() {
  const [messages, setMessages] = useState<UIMessage[]>([initialMessage]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault();
    const content = draft.trim();
    if (!content || isSending) return;

    const userMessage: UIMessage = { id: crypto.randomUUID(), role: "user", content };
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setDraft("");
    setIsSending(true);

    try {
      const response = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages.map(({ role, content: text }) => ({ role, content: text })),
        }),
      });
      const data = (await response.json()) as AgentResult | { error: string };
      if (!response.ok || !("message" in data)) {
        throw new Error("error" in data ? data.error : "Request failed.");
      }

      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.message,
          events: data.events,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: error instanceof Error ? error.message : "Something went wrong. Please try again.",
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  }

  function addVoiceMessage(message: {
    role: "user" | "assistant";
    content: string;
    events?: AgentResult["events"];
  }) {
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        ...message,
      },
    ]);
  }

  return (
    <main className="mx-auto flex h-dvh w-full max-w-2xl flex-col bg-white">
      <header className="raised-surface mx-auto mt-3 flex h-11 shrink-0 items-center justify-center rounded-full px-6">
        <h1 className="text-base font-bold tracking-normal text-slate-900">Claw-Mobile</h1>
      </header>

      <section className="flex-1 overflow-y-auto px-4 py-6 sm:px-6" aria-live="polite">
        <div className="space-y-6">
          {messages.map((message) => <Message key={message.id} message={message} />)}
          {isSending && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span className="size-2 animate-pulse rounded-full bg-sky-400" /> Working…
            </div>
          )}
          <div ref={endRef} />
        </div>
      </section>

      <div className="shrink-0 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 sm:px-5">
        <form onSubmit={sendMessage} className="raised-surface flex items-end gap-2 rounded-[1.4rem] p-2">
          <textarea
            aria-label="Message OpenClaw"
            className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-6 text-slate-900 outline-none placeholder:text-slate-400"
            disabled={isSending}
            maxLength={4000}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Tell OpenClaw where to go…"
            rows={1}
            value={draft}
          />
          <VoiceControl
            messages={messages.map(({ role, content }) => ({ role, content }))}
            onVoiceMessage={addVoiceMessage}
          />
          <button
            aria-label="Send message"
            className="plastic-button flex size-10 shrink-0 items-center justify-center rounded-full text-lg font-black disabled:cursor-not-allowed disabled:opacity-30"
            disabled={!draft.trim() || isSending}
            type="submit"
          >
            ↑
          </button>
        </form>
      </div>
    </main>
  );
}
