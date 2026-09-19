import { NextResponse } from "next/server";
import type { ChatMessage } from "@/agent/run-agent";
import {
  getElevenLabs,
  getElevenLabsConfig,
  getVoiceServerAuthorization,
} from "@/lib/elevenlabs";

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

    if (!Array.isArray(messages) || !messages.every(isChatMessage)) {
      return NextResponse.json({ error: "A valid messages array is required." }, { status: 400 });
    }

    const { apiKey, speechEngineId, internalUrl } = getElevenLabsConfig();
    const tokenResponse = await getElevenLabs().conversationalAi.conversations.getWebrtcToken({
      agentId: speechEngineId,
    });

    const contextResponse = await fetch(`${internalUrl}/internal/context`, {
      method: "POST",
      headers: {
        Authorization: getVoiceServerAuthorization(apiKey),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        conversationId: tokenResponse.conversationId,
        messages: messages.slice(-30),
      }),
      cache: "no-store",
    });

    if (!contextResponse.ok) {
      throw new Error("The voice server is unavailable.");
    }

    return NextResponse.json({ token: tokenResponse.token });
  } catch (error) {
    console.error("Voice token request failed", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Voice could not be started." },
      { status: 500 },
    );
  }
}
