import asyncio
import base64
import json
import os
import subprocess
import time

import websockets
from elevenlabs import AsyncElevenLabs


MIC_DEVICE = "plughw:1,0"
SPEAKER_DEVICE = "plughw:0,0"

INPUT_RATE = 16000
OUTPUT_RATE = 24000

# Small delay after speaker audio ends before reopening mic.
# Prevents the tail/echo of the AI voice being picked up.
MIC_REOPEN_DELAY = 0.12


def load_env(path=".env.local"):
    with open(path, "r") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


async def main():
    load_env()

    api_key = os.environ["ELEVENLABS_API_KEY"]
    engine_id = os.environ["ELEVENLABS_SPEECH_ENGINE_ID"]

    client = AsyncElevenLabs(api_key=api_key)

    print("Getting signed URL...")

    signed = await client.conversational_ai.conversations.get_signed_url(
        agent_id=engine_id
    )

    print("Connecting...")

    # False = user can talk
    # True  = AI audio is playing / microphone must not be sent
    ai_speaking = asyncio.Event()

    # Timestamp of latest received AI audio.
    last_audio_time = 0.0

    async with websockets.connect(
        signed.signed_url,
        max_size=None,
        ping_interval=20,
        ping_timeout=20,
    ) as ws:

        await ws.send(json.dumps({
            "type": "conversation_initiation_client_data"
        }))

        mic = subprocess.Popen(
            [
                "arecord",
                "-D", MIC_DEVICE,
                "-f", "S16_LE",
                "-r", str(INPUT_RATE),
                "-c", "1",
                "-t", "raw",
                "--buffer-size=800",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

        speaker = subprocess.Popen(
            [
                "aplay",
                "-D", SPEAKER_DEVICE,
                "-f", "S16_LE",
                "-r", str(OUTPUT_RATE),
                "-c", "1",
                "-t", "raw",
                "--buffer-size=1200",
            ],
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

        print()
        print("================================")
        print(" ROBOT VOICE ONLINE")
        print("================================")
        print("🎤 Mic ON — speak normally")
        print("CTRL+C to stop")
        print()

        async def send_microphone():
            while True:

                # 50 ms audio chunk:
                # 16000 samples/sec * 2 bytes * 0.05 sec = 1600 bytes
                chunk = await asyncio.to_thread(
                    mic.stdout.read,
                    1600,
                )

                if not chunk:
                    raise RuntimeError("Microphone stopped.")

                # HALF DUPLEX:
                # Never send microphone audio while AI is speaking.
                if ai_speaking.is_set():
                    continue

                await ws.send(json.dumps({
                    "user_audio_chunk":
                        base64.b64encode(chunk).decode("ascii")
                }))

        async def reopen_microphone_after_audio():
            nonlocal last_audio_time

            this_audio_time = last_audio_time

            await asyncio.sleep(MIC_REOPEN_DELAY)

            # More audio arrived while we were waiting.
            if this_audio_time != last_audio_time:
                return

            if ai_speaking.is_set():
                ai_speaking.clear()

                print()
                print("🎤 LISTENING")
                print()

        async def receive_elevenlabs():
            nonlocal last_audio_time

            async for message in ws:

                event = json.loads(message)
                event_type = event.get("type")

                if event_type == "conversation_initiation_metadata":

                    metadata = event.get(
                        "conversation_initiation_metadata_event",
                        {}
                    )

                    print(
                        "Conversation:",
                        metadata.get("conversation_id", "started")
                    )

                    print("🎤 LISTENING")
                    print()

                elif event_type == "user_transcript":

                    transcript = event.get(
                        "user_transcription_event",
                        {}
                    ).get("user_transcript", "")

                    if transcript:
                        print()
                        print("YOU:", transcript)
                        print("🧠 THINKING...")

                elif event_type == "agent_response":

                    response = event.get(
                        "agent_response_event",
                        {}
                    ).get("agent_response", "")

                    if response:
                        print("AI:", response)

                elif event_type == "audio":

                    audio_b64 = event.get(
                        "audio_event",
                        {}
                    ).get("audio_base_64")

                    if not audio_b64:
                        continue

                    # CLOSE MIC BEFORE playing the first byte
                    # of AI speech.
                    if not ai_speaking.is_set():
                        ai_speaking.set()
                        print("🔊 SPEAKING")

                    audio = base64.b64decode(audio_b64)

                    last_audio_time = time.monotonic()

                    await asyncio.to_thread(
                        speaker.stdin.write,
                        audio
                    )

                    await asyncio.to_thread(
                        speaker.stdin.flush
                    )

                    # Each new audio packet effectively resets
                    # the reopen timer.
                    asyncio.create_task(
                        reopen_microphone_after_audio()
                    )

                elif event_type == "interruption":
                    # We intentionally use half-duplex, so this
                    # should become uncommon.
                    print("↳ interruption event")

                elif event_type == "ping":

                    ping = event.get("ping_event", {})

                    await ws.send(json.dumps({
                        "type": "pong",
                        "event_id": ping.get("event_id")
                    }))

                elif event_type == "error":
                    print()
                    print("ELEVENLABS ERROR:")
                    print(json.dumps(event, indent=2))

        try:
            await asyncio.gather(
                send_microphone(),
                receive_elevenlabs(),
            )

        finally:
            mic.terminate()
            speaker.terminate()


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("\nVoice assistant stopped.")
