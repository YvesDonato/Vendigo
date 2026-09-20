"""Persistent Pi entry point using the existing voice agent's public interface."""

import asyncio
import signal

from vendi.config import VoiceConfig
from vendi.conversation.context import VendigoContext
from vendi.errors import VoiceFailure
from vendi.events import EventType
from vendi.voice import VendiVoice
from vendi.voice_state import VoiceState


async def run_forever(voice, has_error=lambda: False):
    """Own input turns serially, staying available between ordinary conversations."""
    try:
        if not await voice.enter_conversation(listen=False):
            raise VoiceFailure("service", "Unable to start a conversation; retrying.")
        while True:
            if has_error():
                raise VoiceFailure("service", "Voice connection or device failed; restarting cleanly.")
            transcript = await voice.test_microphone()
            if has_error():
                raise VoiceFailure("service", "Voice connection or device failed; restarting cleanly.")
            if not transcript:
                # Silence or the core inactivity timer interrupting capture is normal.
                await asyncio.sleep(0.05)
                continue
            if voice.mode == VoiceState.IDLE:
                # Finish cancellation from the previous session before reusing audio.
                await voice.stop_all_audio()
                if not await voice.enter_conversation(listen=False):
                    raise VoiceFailure("service", "Unable to start the next conversation; retrying.")
            # Exactly one listener: capture has closed before greeting/reply playback.
            await voice.handle_transcript(transcript)
    finally:
        await voice.close()


async def main():
    config = VoiceConfig.from_env()
    failed = False

    def event(event):
        nonlocal failed
        if event.type == EventType.LISTENING_READY:
            print("Listening…", flush=True)
        elif event.type == EventType.TRANSCRIPT_RECEIVED:
            print("You:", event.data["text"], flush=True)
        elif event.type == EventType.CONVERSATION_ENDED:
            print("Conversation ended:", event.data["reason"], "— listener remains available.", flush=True)
        elif event.type == EventType.VOICE_ERROR:
            failed = True
            print("Voice error:", event.data["message"], flush=True)

    voice = VendiVoice(config, context=VendigoContext(config.app_url), on_event=event,
                       on_speech=lambda text: print("Vendi:", text, flush=True))
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, task.cancel)
    print("Vendi persistent listener started. Stop with: sudo systemctl stop vendi", flush=True)
    try:
        await run_forever(voice, lambda: failed)
    except asyncio.CancelledError:
        print("Vendi listener stopped by operator.", flush=True)
    finally:
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        # Never expose provider exceptions or environment credentials in the journal.
        print(str(error) if isinstance(error, VoiceFailure) else
              "Vendi listener failed; service manager will retry.", flush=True)
        raise SystemExit(1)
