import { NextResponse } from "next/server";
import {
  getElevenLabsConfig,
  getVoiceServerAuthorization,
} from "@/lib/elevenlabs";

export async function GET(request: Request) {
  try {
    const conversationId = new URL(request.url).searchParams.get("conversationId");
    if (!conversationId || !/^[a-zA-Z0-9_-]{1,200}$/.test(conversationId)) {
      return NextResponse.json({ error: "A valid conversation ID is required." }, { status: 400 });
    }

    const { apiKey, internalUrl } = getElevenLabsConfig();
    const response = await fetch(
      `${internalUrl}/internal/events?conversationId=${encodeURIComponent(conversationId)}`,
      {
        headers: { Authorization: getVoiceServerAuthorization(apiKey) },
        cache: "no-store",
      },
    );

    if (!response.ok) {
      throw new Error("Voice activity could not be loaded.");
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    console.error("Voice events request failed", error);
    return NextResponse.json({ events: [] }, { status: 500 });
  }
}
