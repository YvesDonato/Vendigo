"use client";

import { ConversationProvider, useConversation } from "@elevenlabs/react";
import { getLogger, LoggerNames, LogLevel } from "livekit-client";
import { useCallback, useMemo, useRef, useState } from "react";
import type { ChatMessage, ToolEvent } from "@/agent/run-agent";

type VoiceMessage = ChatMessage & { events?: ToolEvent[] };
type VoiceState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

type VoiceControlProps = {
  messages: ChatMessage[];
  onVoiceMessage: (message: VoiceMessage) => void;
};

const stateLabels: Record<Exclude<VoiceState, "idle">, string> = {
  connecting: "Connecting…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  error: "Voice unavailable",
};

const signalLogger = getLogger(LoggerNames.Signal);

function endSessionWithoutTeardownNoise(endSession: () => void) {
  const previousLevel = signalLogger.getLevel();
  signalLogger.setLevel(LogLevel.silent);
  endSession();
  window.setTimeout(() => signalLogger.setLevel(previousLevel), 1_500);
}

async function getConversationToken(messages: ChatMessage[]) {
  const response = await fetch("/api/voice/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  const data = (await response.json()) as { token?: string; error?: string };

  if (!response.ok || !data.token) {
    throw new Error(data.error ?? "Voice could not be started.");
  }

  return data.token;
}

async function getToolEvents(conversationId: string) {
  const response = await fetch(
    `/api/voice/events?conversationId=${encodeURIComponent(conversationId)}`,
    { cache: "no-store" },
  );
  if (!response.ok) return [];
  const data = (await response.json()) as { events?: ToolEvent[] };
  return data.events ?? [];
}

function VoiceControlInner({ messages, onVoiceMessage }: VoiceControlProps) {
  const [isStarting, setIsStarting] = useState(false);
  const [isAwaitingResponse, setIsAwaitingResponse] = useState(false);
  const [error, setError] = useState<string>();
  const conversationIdRef = useRef<string | undefined>(undefined);
  const lastMessageKeyRef = useRef("");

  const conversation = useConversation({
    onConnect: ({ conversationId }) => {
      conversationIdRef.current = conversationId;
      setIsStarting(false);
      setError(undefined);
    },
    onDisconnect: () => {
      conversationIdRef.current = undefined;
      setIsStarting(false);
      setIsAwaitingResponse(false);
    },
    onError: (message) => {
      setError(message || "Voice could not connect.");
      setIsStarting(false);
      setIsAwaitingResponse(false);
    },
    onInterruption: () => setIsAwaitingResponse(false),
    onMessage: ({ event_id: eventId, message, role }) => {
      const key = `${eventId ?? "none"}:${role}:${message}`;
      if (!message.trim() || lastMessageKeyRef.current === key) return;
      lastMessageKeyRef.current = key;

      if (role === "user") {
        setIsAwaitingResponse(true);
        onVoiceMessage({ role: "user", content: message });
        return;
      }

      setIsAwaitingResponse(false);
      const conversationId = conversationIdRef.current;
      void (async () => {
        const events = conversationId ? await getToolEvents(conversationId) : [];
        onVoiceMessage({ role: "assistant", content: message, events });
      })();
    },
  });

  const voiceState = useMemo<VoiceState>(() => {
    if (error) return "error";
    if (isStarting || conversation.status === "connecting") return "connecting";
    if (conversation.status !== "connected") return "idle";
    if (conversation.isSpeaking) return "speaking";
    if (isAwaitingResponse) return "thinking";
    return "listening";
  }, [conversation.isSpeaking, conversation.status, error, isAwaitingResponse, isStarting]);

  const start = useCallback(async () => {
    try {
      setError(undefined);
      setIsStarting(true);
      setIsAwaitingResponse(false);
      lastMessageKeyRef.current = "";

      const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      permissionStream.getTracks().forEach((track) => track.stop());
      const token = await getConversationToken(messages);
      conversation.startSession({
        conversationToken: token,
        connectionType: "webrtc",
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Microphone access failed.");
      setIsStarting(false);
    }
  }, [conversation, messages]);

  const toggle = useCallback(() => {
    if (voiceState === "idle" || voiceState === "error") {
      void start();
    } else {
      endSessionWithoutTeardownNoise(conversation.endSession);
    }
  }, [conversation, start, voiceState]);

  const isActive = voiceState !== "idle" && voiceState !== "error";

  return (
    <div className="relative flex shrink-0 items-center">
      {voiceState !== "idle" && (
        <div
          className={`voice-status absolute bottom-full right-0 mb-3 flex items-center gap-2 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-semibold ${
            voiceState === "error" ? "text-red-700" : "text-sky-700"
          }`}
          role="status"
          title={error}
        >
          <span
            className={`size-2 rounded-full ${
              voiceState === "error" ? "bg-red-500" : "animate-pulse bg-sky-500"
            }`}
          />
          {stateLabels[voiceState]}
        </div>
      )}
      <button
        aria-label={isActive ? "End voice conversation" : "Start voice conversation"}
        aria-pressed={isActive}
        className={`voice-button flex size-10 items-center justify-center rounded-full ${
          isActive ? "voice-button-active" : ""
        }`}
        onClick={toggle}
        type="button"
      >
        {isActive ? (
          <span className="size-3 rounded-sm bg-current" />
        ) : (
          <svg aria-hidden="true" className="size-5" viewBox="0 0 24 24">
            <path
              d="M12 15.5a3.5 3.5 0 0 0 3.5-3.5V6a3.5 3.5 0 1 0-7 0v6a3.5 3.5 0 0 0 3.5 3.5Zm6-3.5a6 6 0 0 1-12 0M12 18v3m-3 0h6"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeWidth="1.8"
            />
          </svg>
        )}
      </button>
    </div>
  );
}

export function VoiceControl(props: VoiceControlProps) {
  return (
    <ConversationProvider>
      <VoiceControlInner {...props} />
    </ConversationProvider>
  );
}
