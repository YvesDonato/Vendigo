"""ElevenLabs Scribe realtime: final utterances only, with patient silence detection."""

import asyncio
import base64
import json
from urllib.parse import urlencode

from vendi.audio.backend import wav_chunks, wav_format
from vendi.errors import VoiceFailure
from vendi.speech.turn import TurnProgress, is_hesitation


class ScribeSTT:
    def __init__(self, config, connect=None):
        self.config = config
        self._connect = connect
        self.max_turn_timeout = config.max_utterance + config.request_timeout * 2

    def _connection(self, rate):
        if not self.config.elevenlabs_api_key:
            raise VoiceFailure("stt", "Set ELEVENLABS_API_KEY for realtime speech recognition, or VENDI_STT_PROVIDER=vosk for offline STT.")
        if self._connect is None:
            try:
                from websockets.asyncio.client import connect
            except ImportError as error:
                raise VoiceFailure("stt", "Install vendi/requirements.txt for realtime STT.") from error
            self._connect = connect
        query = urlencode({
            "model_id": self.config.stt_model, "audio_format": f"pcm_{rate}", "language_code": "en",
            "commit_strategy": "vad", "vad_silence_threshold_secs": self.config.end_silence,
            "vad_threshold": 0.4, "min_speech_duration_ms": 200, "min_silence_duration_ms": 200,
        })
        return self._connect(
            "wss://api.elevenlabs.io/v1/speech-to-text/realtime?" + query,
            additional_headers={"xi-api-key": self.config.elevenlabs_api_key},
            open_timeout=self.config.request_timeout, close_timeout=1, max_size=1_048_576,
        )

    @staticmethod
    def _check_error(event):
        kind = event.get("message_type", "")
        if "error" in kind or kind in {"auth_error", "quota_exceeded", "rate_limited", "unaccepted_terms"}:
            # Provider messages can contain request details; only emit our own safe text.
            raise VoiceFailure("stt", "ElevenLabs realtime STT rejected the session; check key permissions, account terms, and quota.")

    async def transcribe(self, chunks):
        return await self.transcribe_turn(chunks, self.config.listen_timeout)

    async def transcribe_file(self, path):
        rate, channels = wav_format(path)
        if channels != 1 or rate not in (8000, 16000, 22050, 24000, 44100, 48000):
            raise VoiceFailure("stt", "STT fixtures must be mono PCM WAV at a supported sample rate.")
        async def paced_audio():
            source = wav_chunks(path)
            try:
                async for block in source:
                    yield block
                    await asyncio.sleep(len(block) / (rate * 2))
                # Final trailing silence lets VAD commit the complete last sentence.
                for _ in range(int((self.config.end_silence + 1) * 10)):
                    yield b"\0" * (rate // 10 * 2)
                    await asyncio.sleep(0.1)
            finally:
                await source.aclose()
        return await self.transcribe_turn(paced_audio(), self.config.listen_timeout, rate=rate)

    async def transcribe_turn(self, chunks, idle_timeout, on_activity=lambda: None, on_ready=lambda: None, rate=16000):
        tasks = []
        try:
            async with self._connection(rate) as socket:
                first = json.loads(await asyncio.wait_for(socket.recv(), self.config.request_timeout))
                self._check_error(first)
                if first.get("message_type") != "session_started":
                    raise VoiceFailure("stt", "Realtime STT did not start a valid session.")
                progress = TurnProgress(idle_timeout, self.config.max_utterance,
                                        self.config.speech_rms_threshold, on_activity)
                segments = []
                pending_partial = ""
                committed_revision = -1

                async def send_audio():
                    buffer = bytearray()
                    first_chunk = True
                    try:
                        on_ready()
                        async for block in chunks:
                            if len(block) % 2:
                                raise VoiceFailure("stt", "Microphone returned an incomplete PCM frame.")
                            progress.audio(block, rate)
                            buffer.extend(block)
                            # 100 ms mono PCM frames; no full-utterance upload delay.
                            size = rate // 10 * 2
                            while len(buffer) >= size:
                                data = bytes(buffer[:size])
                                del buffer[:size]
                                message = {
                                    "message_type": "input_audio_chunk", "sample_rate": rate,
                                    "audio_base_64": base64.b64encode(data).decode("ascii"),
                                }
                                if first_chunk:
                                    message["previous_text"] = "Vendi, a Vendigo street snack vendor."
                                    first_chunk = False
                                await socket.send(json.dumps(message))
                        if buffer:
                            await socket.send(json.dumps({"message_type": "input_audio_chunk", "sample_rate": rate,
                                "audio_base_64": base64.b64encode(buffer).decode("ascii")}))
                    finally:
                        # Sender must close the microphone BEFORE this recognizer returns.
                        await chunks.aclose()

                async def receive_text():
                    nonlocal pending_partial, committed_revision
                    async for message in socket:
                        event = json.loads(message)
                        self._check_error(event)
                        kind = event.get("message_type")
                        text = event.get("text", "")
                        if not isinstance(text, str):
                            raise VoiceFailure("stt", "Realtime STT returned an invalid transcript.")
                        if kind == "partial_transcript":
                            pending_partial = text.strip()
                            progress.partial(text)
                        elif kind == "committed_transcript" and text.strip():
                            pending_partial = ""
                            progress.last_partial = ""
                            if is_hesitation(text):
                                progress.partial(text)
                                continue  # Keep the same microphone session through "um…" / "hold on".
                            segments.append(text.strip())
                            committed_revision = progress.audio_revision
                            on_activity()
                            # Commits are segments. Do not answer over ongoing local speech.
                    raise VoiceFailure("stt", "Realtime STT disconnected before the sentence finished.")

                async def watch_silence():
                    while not progress.expired():
                        last_voice = progress.last_audio_speech if progress.last_audio_speech is not None else progress.last_speech
                        if (segments and not pending_partial and progress.audio_revision == committed_revision
                                and last_voice is not None and progress.clock() - last_voice >= self.config.end_silence):
                            return " ".join(segments)
                        await asyncio.sleep(0.05)
                    return ""

                sender = asyncio.create_task(send_audio())
                receiver = asyncio.create_task(receive_text())
                timer = asyncio.create_task(watch_silence())
                tasks = [sender, receiver, timer]
                try:
                    pending = set(tasks)
                    while pending:
                        completed, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                        # Microphone/provider errors take precedence over partial success.
                        for task in completed:
                            if task.exception() is not None:
                                raise task.exception()
                        if receiver in completed:
                            return receiver.result()
                        if timer in completed:
                            return timer.result()
                        # A finite dev audio source may finish before the server commits.
                    return ""
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except VoiceFailure:
            raise
        except Exception as error:
            raise VoiceFailure("stt", "Realtime speech recognition failed; check the connection and ElevenLabs access.") from error
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self):
        # Connections belong to individual listening turns and always close in their context.
        pass
