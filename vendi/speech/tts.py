"""ElevenLabs streaming PCM, complete-file atomic caching, and pre-generation."""

import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
import uuid
import wave

from vendi.audio.backend import wav_chunks, wav_format
from vendi.audio.speech_pcm import trim_speech
from vendi.errors import VoiceFailure
from vendi.speech.pronunciation import speech_text


RATE = 24000
VOICE_SETTINGS = {"stability": 0.5, "similarity_boost": 0.8, "style": 0.0,
                  "use_speaker_boost": True, "speed": 1.0}


class ElevenLabsTTS:
    def __init__(self, config, client=None):
        self.config = config
        self._client = client
        self._owns_client = client is None
        identity = json.dumps([config.elevenlabs_voice_id, config.elevenlabs_model, VOICE_SETTINGS, RATE,
                               "spoken-prices-v1"], sort_keys=True)
        self.voice_key = hashlib.sha256(identity.encode()).hexdigest()[:16]

    def cache_path(self, text):
        key = hashlib.sha256(speech_text(text).encode()).hexdigest()
        return self.config.cache_dir / "speech" / self.voice_key / f"{key}.wav"

    def phrase_path(self, phrase):
        key = hashlib.sha256(speech_text(phrase.text).encode()).hexdigest()[:12]
        return self.config.clips_dir / self.voice_key / phrase.category / f"{phrase.id}-{key}.wav"

    def _http(self):
        if self._client is None:
            try:
                import httpx
            except ImportError as error:
                raise VoiceFailure("tts", "Install vendi/requirements.txt for ElevenLabs speech.") from error
            self._client = httpx.AsyncClient(timeout=self.config.request_timeout)
        return self._client

    async def stream(self, text, output_path=None, cached_only=False):
        # Generated files can have seconds of quiet padding. Do not keep the mic
        # gated on that padding after the customer has heard Vendi finish speaking.
        source = self._raw_stream(text, output_path, cached_only)
        trimmed = trim_speech(source, RATE)
        try:
            async for data in trimmed:
                yield data
        finally:
            await trimmed.aclose()

    async def _raw_stream(self, text, output_path=None, cached_only=False):
        text = text.strip()
        if not text or len(text) > 1200:
            raise VoiceFailure("tts", "Speech text must contain 1–1200 characters.")
        text = speech_text(text)
        path = Path(output_path) if output_path else self.cache_path(text)
        if path.is_file():
            try:
                if wav_format(path) != (RATE, 1):
                    raise ValueError("Wrong format")
                # Check for a truncated file, not just a valid WAV header.
                with wave.open(str(path), "rb") as audio:
                    if len(audio.readframes(audio.getnframes())) != audio.getnframes() * 2:
                        raise ValueError("Truncated file")
            except (OSError, EOFError, ValueError, wave.Error, VoiceFailure):
                path.unlink(missing_ok=True)
            else:
                async for data in wav_chunks(path):
                    yield data
                return
        if cached_only:
            raise VoiceFailure("tts", "Fallback clip missing. Run python3 -m vendi.voice_demo --generate-clips.")
        if not self.config.elevenlabs_api_key or not self.config.elevenlabs_voice_id:
            raise VoiceFailure("tts", "Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID, then generate Vendi's clips.")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            with wave.open(str(temporary), "wb") as audio:
                audio.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
                async with self._http().stream(
                    "POST", f"https://api.elevenlabs.io/v1/text-to-speech/{quote(self.config.elevenlabs_voice_id, safe='')}/stream",
                    params={"output_format": "pcm_24000"},
                    headers={"xi-api-key": self.config.elevenlabs_api_key},
                    json={"text": text, "model_id": self.config.elevenlabs_model, "voice_settings": VOICE_SETTINGS},
                ) as response:
                    response.raise_for_status()
                    pending = b""
                    size = 0
                    async for chunk in response.aiter_bytes():
                        pending += chunk
                        count = len(pending) - len(pending) % 2
                        if not count:
                            continue
                        data, pending = pending[:count], pending[count:]
                        size += len(data)
                        if size > RATE * 2 * 60:
                            raise VoiceFailure("tts", "Speech exceeded the 60-second audio limit.")
                        audio.writeframesraw(data)
                        yield data  # Speaker receives first PCM without waiting for the entire response.
                    if not size or pending:
                        raise VoiceFailure("tts", "ElevenLabs returned empty or incomplete audio.")
            temporary.replace(path)
            if output_path is None:
                self._prune(path.parent)
        except VoiceFailure:
            raise
        except Exception as error:
            raise VoiceFailure("tts", "ElevenLabs speech failed; check connectivity, voice ID, and account access.") from error
        finally:
            temporary.unlink(missing_ok=True)

    def _prune(self, directory):
        paths = sorted(directory.glob("*.wav"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths[self.config.max_cached_clips:]:
            path.unlink(missing_ok=True)

    async def generate_clip(self, text, output_path):
        async def generate():
            async for _ in self.stream(text, output_path):
                pass
        await asyncio.wait_for(generate(), timeout=max(60, self.config.request_timeout))
        return Path(output_path)

    async def close(self):
        if self._client is not None and self._owns_client:
            await self._client.aclose()


class SilentTTS:
    """Explicit demo stub; never pretends synthetic silence is ElevenLabs speech."""

    def phrase_path(self, phrase):
        return None

    async def stream(self, text, output_path=None, cached_only=False):
        yield b"\0" * 480

    async def close(self):
        pass
