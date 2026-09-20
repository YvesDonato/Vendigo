"""Local streaming STT, using the Vosk approach already present in food_robot/."""

import asyncio
from collections import deque
import json
from pathlib import Path
from typing import AsyncIterator, Protocol
import warnings

from vendi.audio.backend import wav_chunks, wav_format
from vendi.errors import VoiceFailure
from vendi.speech.turn import TurnProgress, is_hesitation


class SpeechToText(Protocol):
    async def transcribe(self, chunks: AsyncIterator[bytes]) -> str: ...


class VoskSTT:
    def __init__(self, model_path, end_silence=1.2, max_utterance=45, speech_rms_threshold=250):
        self.model_path = model_path
        self._model = None
        self.end_silence = end_silence
        self.max_utterance = max_utterance
        self.speech_rms_threshold = speech_rms_threshold
        self.max_turn_timeout = max_utterance + 30

    async def prepare(self):
        if self._model is not None:
            return
        if not self.model_path or not Path(self.model_path).is_dir():
            raise VoiceFailure("stt", "Set VENDI_VOSK_MODEL_PATH to an unpacked English Vosk model.")
        try:
            # Vosk is local; its unused requests import warns on Apple's system Python.
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL.*")
                from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            self._model = await asyncio.to_thread(Model, self.model_path)
        except Exception as error:
            raise VoiceFailure("stt", "Vosk model could not load; check installation and model path.") from error

    async def transcribe_turn(self, chunks, idle_timeout, on_activity=lambda: None, on_ready=lambda: None):
        await self.prepare()
        from vosk import KaldiRecognizer
        recognizer = KaldiRecognizer(self._model, 16000)
        progress = TurnProgress(idle_timeout, self.max_utterance, self.speech_rms_threshold, on_activity)
        segments = []
        on_ready()
        async for chunk in chunks:
            progress.audio(chunk)
            if recognizer.AcceptWaveform(chunk):
                text = json.loads(recognizer.Result()).get("text", "").strip()
                if text:
                    segments.append(text)
                    progress.partial(text)
            else:
                progress.partial(json.loads(recognizer.PartialResult()).get("partial", ""))
            if progress.expired():
                return ""
            if progress.last_speech is not None and progress.clock() - progress.last_speech >= self.end_silence:
                final = json.loads(recognizer.FinalResult()).get("text", "").strip()
                text = " ".join(segments + ([final] if final else []))
                if text and not is_hesitation(text):
                    return text
                # An endpoint or hesitation is not necessarily the end of a customer turn.
                segments.clear()
                recognizer = KaldiRecognizer(self._model, 16000)
                progress.last_speech = None
                progress.last_partial = ""
        final = json.loads(recognizer.FinalResult()).get("text", "").strip()
        return " ".join(segments + ([final] if final else []))

    async def transcribe_file(self, path):
        """Dev fixture input; no microphone or speaker is opened."""
        rate, channels = wav_format(path)
        if channels != 1:
            raise VoiceFailure("stt", "STT fixtures must be mono 16-bit PCM WAV files.")
        source = wav_chunks(path)
        try:
            return await self.transcribe(source, rate=rate)
        finally:
            await source.aclose()

    async def transcribe(self, chunks, rate=16000):
        await self.prepare()
        try:
            from vosk import KaldiRecognizer
            recognizer = KaldiRecognizer(self._model, rate)
            # Unrestricted vocabulary avoids forcing ambiguous speech into yes/no.
            async for chunk in chunks:
                if recognizer.AcceptWaveform(chunk):
                    text = json.loads(recognizer.Result()).get("text", "").strip()
                    if text:
                        return text
            return json.loads(recognizer.FinalResult()).get("text", "").strip()
        except VoiceFailure:
            raise
        except Exception as error:
            raise VoiceFailure("stt", "Speech recognition failed; try speaking again.") from error


class ScriptedSTT:
    def __init__(self, transcripts=()):
        self.transcripts = deque(transcripts)

    async def transcribe(self, chunks):
        # Exercise mic ownership even in the offline demo.
        async for _ in chunks:
            return self.transcripts.popleft() if self.transcripts else ""
        return ""
