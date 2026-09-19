import asyncio
import base64
import json
import os
import subprocess

import websockets
from elevenlabs import AsyncElevenLabs


MIC_DEVICE = "plughw:1,0"
SPEAKER_DEVICE = "plughw:0,0"

INPUT_RATE = 16000
OUTPUT_RATE = 24000


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

    print("Getting ElevenLabs signed URL...")

    client = AsyncElevenLabs(api_key=api_key)

    signed = await client.conversational_ai.conversations.get_signed_url(
        agent_id=engine_id
    )

    print("Connecting to ElevenLabs...")

    async with websockets.connect(
        signed.signed_url,
        max_size=None,
    ) as ws:

        await ws.send(json.dumps({
            "type": "conversation_initiation_client_data"
        }))

        print("Connected.")
        print()
        print("Starting microphone and speaker...")
        print("Talk normally.")
        print("Press CTRL+C to stop.")
        print()

        mic = subprocess.Popen(
            [
                "arecord",
                "-D", MIC_DEVICE,
                "-f", "S16_LE",
                "-r", str(INPUT_RATE),
                "-c", "1",
                "-t", "raw",
                "--buffer-size=1600",
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
                "--buffer-size=2400",
            ],
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

        async def send_microphone():
            while True:
                # 100 ms of 16 kHz, mono, 16-bit PCM
                chunk = await asyncio.to_thread(
                    mic.stdout.read,
                    3200,
                )

                if not chunk:
                    raise RuntimeError("Microphone stopped.")

                await ws.send(json.dumps({
                    "user_audio_chunk":
                        base64.b64encode(chunk).decode("ascii")
                }))

        async def receive_elevenlabs():
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

                    print(
                        "Input format:",
                        metadata.get("user_input_audio_format")
                    )

                    print(
                        "Output format:",
                        metadata.get("agent_output_audio_format")
                    )

                    print()
                    print("🎤 LISTENING...")
                    print()

                elif event_type == "user_transcript":
                    transcript = event.get(
                        "user_transcription_event",
                        {}
                    ).get("user_transcript", "")

                    print()
                    print("YOU:", transcript)
                    print("AI: thinking...")

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

                    if audio_b64:
                        audio = base64.b64decode(audio_b64)

                        await asyncio.to_thread(
                            speaker.stdin.write,
                            audio
                        )

                        await asyncio.to_thread(
                            speaker.stdin.flush
                        )

                elif event_type == "interruption":
                    print()
                    print("↳ interrupted")

                elif event_type == "error":
                    print()
                    print("ELEVENLABS ERROR:")
                    print(json.dumps(event, indent=2))

                elif event_type == "ping":
                    ping = event.get("ping_event", {})

                    pong = {
                        "type": "pong",
                        "event_id": ping.get("event_id")
                    }

                    await ws.send(json.dumps(pong))

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
