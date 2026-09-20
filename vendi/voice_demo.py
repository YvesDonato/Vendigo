"""Laptop demo: python3 -m vendi.voice_demo (offline by default)."""

import argparse
import asyncio
from dataclasses import asdict
import json
import sys

from vendi.audio.backend import SilentBackend, sounddevice
from vendi.config import VoiceConfig
from vendi.conversation.agent import DemoAgent
from vendi.conversation.context import ApplicationContext, InventoryItem, StaticContext, VendigoContext
from vendi.events import EventType
from vendi.speech.stt import ScriptedSTT, VoskSTT
from vendi.speech.scribe import ScribeSTT
from vendi.speech.tts import SilentTTS
from vendi.voice import VendiVoice
from vendi.voice_state import VoiceState


async def prompt(message):
    # add_reader keeps timers responsive and avoids an uncancellable input worker on POSIX.
    loop = asyncio.get_running_loop()
    print(message, end="", flush=True)
    if sys.platform == "win32":
        return await asyncio.to_thread(sys.stdin.readline)
    future = loop.create_future()
    def ready():
        if not future.done():
            future.set_result(sys.stdin.readline())
    loop.add_reader(sys.stdin, ready)
    try:
        return await future
    finally:
        loop.remove_reader(sys.stdin)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Use real ElevenLabs, GPT, and audio devices")
    parser.add_argument("--no-audio", action="store_true", help="Disable audio devices; real TTS/GPT remain enabled with --live")
    parser.add_argument("--command", choices=("roam", "sales", "yes", "no", "wake", "tts", "stt", "purchase"))
    parser.add_argument("--text", action="append", help="Typed turn (repeat for multiple turns)")
    parser.add_argument("--duration", type=float, default=20, help="Roaming demo duration in seconds")
    parser.add_argument("--mic", action="store_true", help="Use microphone conversation after the wake trigger")
    parser.add_argument("--wake-listening", action="store_true", help="Experimental wake listening in silent roaming gaps")
    parser.add_argument("--generate-clips", action="store_true", help="Generate/reuse the full ElevenLabs phrase library")
    parser.add_argument("--check-providers", action="store_true", help="One real TTS clip and one GPT turn; no device access")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--transcribe-file", help="Test the configured STT using a mono PCM WAV, without microphone access")
    parser.add_argument("--debug", action="store_true", help="Print raw JSON lifecycle events")
    parser.add_argument("--smoke", action="store_true", help="Exercise all seven paths offline, no keys or dependencies")
    parser.add_argument("--app-url", help="Use current facts from this Vendigo server's GET /api/state")
    parser.add_argument("--robot-id", default="robot-001")
    args = parser.parse_args()
    if not 0 < args.duration <= 3600:
        parser.error("--duration must be between 0 and 3600 seconds")
    if args.smoke and (args.live or args.generate_clips or args.check_providers):
        parser.error("--smoke is an offline check; run provider checks separately")
    if args.no_audio and args.mic:
        parser.error("--no-audio and --mic cannot be combined")
    return args


async def run_command(voice, command, args):
    if command == "roam":
        await voice.start_roaming(wake_listening=args.wake_listening)
        await asyncio.sleep(args.duration)
        await voice.stop_all_audio()
    elif command == "sales":
        await voice.play_sales_line()
    elif command in ("yes", "no"):
        await voice.say_customer_greeting()
        await voice.ask_purchase_question(transcripts=args.text or [command])
    elif command == "purchase":
        await voice.say_customer_greeting()
        await voice.ask_purchase_question()
    elif command == "wake":
        await voice.feed_wake_transcript("Hey Vendi", listen=args.mic)
        if args.mic:
            print("Speak after Vendi finishes. Say 'bye' to finish; silence also times out.")
            while voice.mode == VoiceState.CONVERSATION:
                await asyncio.sleep(0.1)
        elif args.text:
            for text in args.text:
                await voice.handle_transcript(text)
            await voice.end_conversation()
        else:
            print("Typed conversation. Say 'bye' to finish.")
            while voice.mode == VoiceState.CONVERSATION:
                text = await prompt("You: ")
                if not text:
                    await voice.end_conversation()
                    break
                await voice.handle_transcript(text.strip())
    elif command == "tts":
        await voice.speak((args.text or ["Hungry? Good. I happen to know a guy."])[0])
    elif command == "stt":
        print("Speak now. This capture ends automatically.")
        transcript = await voice.test_microphone()
        print("Heard:", transcript or "(silence or device unavailable)")


async def main(args):
    config = VoiceConfig.from_env()
    if args.list_devices:
        print(sounddevice().query_devices())
        return 0
    if args.transcribe_file:
        stt = ScribeSTT(config) if config.stt_provider == "elevenlabs" else VoskSTT(config.vosk_model_path)
        print("Heard:", await stt.transcribe_file(args.transcribe_file))
        return 0
    failures = []
    def event(event):
        if args.debug:
            print(json.dumps(asdict(event)), flush=True)
        elif event.type == EventType.LISTENING_READY:
            print("Listening…", flush=True)
        elif event.type == EventType.TRANSCRIPT_RECEIVED:
            print("You:", event.data["text"], flush=True)
        elif event.type == EventType.VOICE_ERROR:
            print("Voice error:", event.data["message"], flush=True)
        elif event.type == EventType.CONVERSATION_ENDED:
            print("Conversation ended:", event.data["reason"], flush=True)
        if event.type == EventType.VOICE_ERROR:
            failures.append(event)

    demo_context = StaticContext(ApplicationContext(
        inventory=[InventoryItem("demo-chips", "Demo chips", 4)], prices={"demo-chips": 0},
        inventory_known=True, robot_state="ROAMING",
    ))
    context = (VendigoContext(args.app_url or config.app_url, args.robot_id)
               if args.app_url or args.live or args.check_providers else demo_context)
    if args.live or args.generate_clips or args.check_providers:
        print(f"Vendi · {config.stt_provider} STT · {config.end_silence:g}s end-of-turn pause · Ctrl+C to stop", flush=True)
        voice = VendiVoice(config, context=context, on_event=event, on_speech=lambda text: print("Vendi:", text, flush=True),
                           backend=SilentBackend() if args.no_audio or args.check_providers else None)
    else:
        print("OFFLINE DEMO: audio, STT, GPT, and inventory are simulated. No network or robot access.")
        voice = VendiVoice(config, backend=SilentBackend(), tts=SilentTTS(),
                           stt=ScriptedSTT(["yes"]), agent=DemoAgent(context), on_event=event,
                           on_speech=lambda text: print("Vendi:", text))
    try:
        if args.generate_clips:
            # Error clips first: subsequent network failure still has an offline fallback.
            phrases = sorted(voice.phrases.all(), key=lambda p: p.category != "errors")
            for phrase in phrases:
                await voice.tts.generate_clip(phrase.text, voice.tts.phrase_path(phrase))
                print(f"Ready: {phrase.category}/{phrase.id}")
            print(f"Ready: {len(phrases)} ElevenLabs clips for voice {config.elevenlabs_voice_id}.")
        elif args.check_providers:
            phrase = voice.phrases.choose("errors")
            await voice.tts.generate_clip(phrase.text, voice.tts.phrase_path(phrase))
            print("ElevenLabs: generated a complete WAV clip.")
            reply = await voice.agent.respond("Tell me a quick joke about being a robot vendor.")
            print(f"OpenAI ({config.openai_model}): {reply.text}")
        elif args.smoke:
            args.duration = 0.03
            args.text = ["Tell me a joke", "okay thanks"]
            for command in ("roam", "sales", "yes", "no", "wake", "tts", "stt"):
                if command in ("yes", "no"):
                    text, args.text = args.text, None
                    await run_command(voice, command, args)
                    args.text = text
                else:
                    await run_command(voice, command, args)
            print("All seven offline demo paths completed.")
        elif args.command:
            await run_command(voice, args.command, args)
        else:
            commands = {"1": "roam", "2": "sales", "3": "yes", "4": "no", "5": "wake", "6": "tts", "7": "stt", "8": "purchase"}
            while True:
                print("\n1 roaming  2 sales line  3 YES  4 NO  5 Hey Vendi  6 TTS  7 microphone/STT  8 spoken purchase  q quit")
                choice = (await prompt("> ")).strip().lower()
                if choice in ("", "q", "quit"):
                    break
                if choice in commands:
                    await run_command(voice, commands[choice], args)
        return 1 if failures else 0
    finally:
        await voice.close()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main(arguments())))
    except KeyboardInterrupt:
        print("\nVendi voice stopped.")
    except Exception as error:
        # Do not print provider tracebacks containing request headers or environment values.
        from vendi.errors import VoiceFailure
        print(str(error) if isinstance(error, VoiceFailure) else "Voice demo failed; check configuration and dependencies.", file=sys.stderr)
        raise SystemExit(1)
