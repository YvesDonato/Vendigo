import { createHash, timingSafeEqual } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { ElevenLabsClient } from "@elevenlabs/elevenlabs-js";
import { runAgent, type ChatMessage, type ToolEvent } from "../src/agent/run-agent.ts";

for (const filename of [".env.local", ".env"]) {
  try {
    process.loadEnvFile(filename);
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? error.code : undefined;
    if (code !== "ENOENT") throw error;
  }
}

const apiKey = process.env.ELEVENLABS_API_KEY;
const engineId = process.env.ELEVENLABS_SPEECH_ENGINE_ID;
const port = Number(process.env.VOICE_SERVER_PORT ?? 3001);

if (!apiKey || !engineId) {
  throw new Error("ELEVENLABS_API_KEY and ELEVENLABS_SPEECH_ENGINE_ID are required.");
}

if (!Number.isInteger(port) || port < 1 || port > 65_535) {
  throw new Error("VOICE_SERVER_PORT must be a valid port number.");
}

const internalToken = createHash("sha256")
  .update(`openclaw-voice:${apiKey}`)
  .digest("hex");
const contexts = new Map<string, ChatMessage[]>();
const toolEvents = new Map<string, ToolEvent[]>();

function isAuthorized(request: IncomingMessage) {
  const value = request.headers.authorization?.replace(/^Bearer\s+/i, "") ?? "";
  const received = Buffer.from(value);
  const expected = Buffer.from(internalToken);
  return received.length === expected.length && timingSafeEqual(received, expected);
}

function respond(response: ServerResponse, status: number, body: unknown) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  response.end(JSON.stringify(body));
}

async function readJson(request: IncomingMessage) {
  const chunks: Buffer[] = [];
  let size = 0;

  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > 128_000) throw new Error("Request body is too large.");
    chunks.push(buffer);
  }

  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown;
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== "object") return false;
  const message = value as Record<string, unknown>;
  return (
    (message.role === "user" || message.role === "assistant") &&
    typeof message.content === "string" &&
    message.content.trim().length > 0 &&
    message.content.length <= 4_000
  );
}

const httpServer = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);

    if (!url.pathname.startsWith("/internal/") || !isAuthorized(request)) {
      respond(response, 404, { error: "Not found." });
      return;
    }

    if (request.method === "POST" && url.pathname === "/internal/context") {
      const body = await readJson(request);
      const conversationId =
        body && typeof body === "object" && "conversationId" in body
          ? (body as { conversationId?: unknown }).conversationId
          : undefined;
      const messages =
        body && typeof body === "object" && "messages" in body
          ? (body as { messages?: unknown }).messages
          : undefined;

      if (
        typeof conversationId !== "string" ||
        !Array.isArray(messages) ||
        !messages.every(isChatMessage)
      ) {
        respond(response, 400, { error: "Invalid voice context." });
        return;
      }

      contexts.set(conversationId, messages.slice(-30));
      respond(response, 204, null);
      return;
    }

    if (request.method === "GET" && url.pathname === "/internal/events") {
      const conversationId = url.searchParams.get("conversationId") ?? "";
      const events = toolEvents.get(conversationId) ?? [];
      toolEvents.delete(conversationId);
      respond(response, 200, { events });
      return;
    }

    respond(response, 404, { error: "Not found." });
  } catch (error) {
    console.error("Voice server HTTP error", error);
    respond(response, 500, { error: "Voice server request failed." });
  }
});

const elevenlabs = new ElevenLabsClient({ apiKey });
const engine = await elevenlabs.speechEngine.get(engineId);

const attachment = engine.attach(httpServer, "/ws", {
  debug: process.env.NODE_ENV !== "production",
  onInit(conversationId) {
    console.log(`Voice session started: ${conversationId}`);
  },
  async onTranscript(transcript, signal, session) {
    const conversationId = session.conversationId;
    if (!conversationId) return;

    try {
      const voiceMessages: ChatMessage[] = transcript.map((message) => ({
        role: message.role === "agent" ? "assistant" : "user",
        content: message.content,
      }));
      const result = await runAgent({
        messages: [...(contexts.get(conversationId) ?? []), ...voiceMessages].slice(-30),
        signal,
      });

      if (signal.aborted) return;
      toolEvents.set(conversationId, result.events);
      await session.sendResponse(result.message);
    } catch (error) {
      if (signal.aborted) return;
      console.error("Voice agent turn failed", error);
      await session.sendResponse("Sorry, I couldn't complete that. Please try again.");
    }
  },
  onClose(session) {
    if (session.conversationId) contexts.delete(session.conversationId);
    console.log(`Voice session ended: ${session.conversationId ?? "unknown"}`);
  },
  onDisconnect(session) {
    if (session.conversationId) contexts.delete(session.conversationId);
    console.warn(`Voice session disconnected: ${session.conversationId ?? "unknown"}`);
  },
  onError(error) {
    console.error("Speech Engine error", error);
  },
});

httpServer.listen(port, () => {
  console.log(`OpenClaw voice server listening on http://127.0.0.1:${port}/ws`);
});

async function shutdown() {
  await attachment.close();
  await new Promise<void>((resolve, reject) => {
    httpServer.close((error) => (error ? reject(error) : resolve()));
  });
}

process.once("SIGINT", () => void shutdown().finally(() => process.exit(0)));
process.once("SIGTERM", () => void shutdown().finally(() => process.exit(0)));
