import { NextResponse } from "next/server";
import { runAgent, type ChatMessage } from "@/agent/run-agent";
import { inventoryFromSnapshot } from "@/agent/live-inventory";
import { getStore } from "@/lib/server/runtime";

const isChatMessage = (value: unknown): value is ChatMessage => {
  if (!value || typeof value !== "object") return false;
  const message = value as Record<string, unknown>;
  return (
    (message.role === "user" || message.role === "assistant") &&
    typeof message.content === "string" &&
    message.content.trim().length > 0 &&
    message.content.length <= 4_000
  );
};

export async function POST(request: Request) {
  try {
    const body: unknown = await request.json();
    const messages =
      body && typeof body === "object" && "messages" in body
        ? (body as { messages?: unknown }).messages
        : undefined;

    if (!Array.isArray(messages) || messages.length === 0 || !messages.every(isChatMessage)) {
      return NextResponse.json({ error: "A valid messages array is required." }, { status: 400 });
    }

    if (!process.env.OPENAI_API_KEY) {
      return NextResponse.json({ error: "OPENAI_API_KEY is not configured." }, { status: 500 });
    }

    const result = await runAgent({
      messages: messages.slice(-30),
      signal: request.signal,
      inventorySource: async () => inventoryFromSnapshot(await getStore().snapshot()),
    });
    return NextResponse.json(result);
  } catch (error) {
    console.error("Agent request failed", error);
    return NextResponse.json(
      { error: "OpenClaw couldn't complete that request. Please try again." },
      { status: 500 },
    );
  }
}
