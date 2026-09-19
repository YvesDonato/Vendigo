import "server-only";

import { createHash } from "node:crypto";
import { ElevenLabsClient } from "@elevenlabs/elevenlabs-js";

let client: ElevenLabsClient | undefined;

export function getElevenLabsConfig() {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  const speechEngineId = process.env.ELEVENLABS_SPEECH_ENGINE_ID;

  if (!apiKey || !speechEngineId) {
    throw new Error("ElevenLabs voice is not configured.");
  }

  return {
    apiKey,
    speechEngineId,
    internalUrl: process.env.VOICE_SERVER_INTERNAL_URL ?? "http://127.0.0.1:3001",
  };
}

export function getElevenLabs() {
  const { apiKey } = getElevenLabsConfig();
  client ??= new ElevenLabsClient({ apiKey });
  return client;
}

export function getVoiceServerAuthorization(apiKey: string) {
  const token = createHash("sha256")
    .update(`openclaw-voice:${apiKey}`)
    .digest("hex");
  return `Bearer ${token}`;
}
