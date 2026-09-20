"""PortAudio devices are opened only for the duration of the owner's audio job."""

import asyncio
import queue
import threading
import wave
from typing import AsyncIterator, Protocol

from vendi.errors import VoiceFailure


class AudioBackend(Protocol):
    async def play(self, chunks: AsyncIterator[bytes], rate: int, channels: int = 1): ...
    def capture(self, rate: int = 16000) -> AsyncIterator[bytes]: ...


def sounddevice():
    try:
        import sounddevice as sd
        return sd
    except (ImportError, OSError) as error:
        raise VoiceFailure("audio", "Install vendi/requirements.txt and the PortAudio system library.") from error


def device_id(value):
    return int(value) if value and value.isdecimal() else (value or None)


class SoundDeviceBackend:
    realtime = True

    def __init__(self, input_device="", output_device=""):
        self.input_device = device_id(input_device)
        self.output_device = device_id(output_device)

    async def play(self, chunks, rate, channels=1):
        sd = sounddevice()
        loop = asyncio.get_running_loop()
        blocks = queue.Queue(maxsize=12)
        done = threading.Event()
        finished = asyncio.Event()
        current = b""
        stream = None
        started = False
        buffered = 0
        prebuffer_bytes = min(int(rate * channels * 2 * 0.12), 4096 * 4)

        def playback_finished():
            # PortAudio's void callback must return None, not asyncio's Handle.
            loop.call_soon_threadsafe(finished.set)

        def callback(outdata, frames, timing, status):
            nonlocal current
            outdata[:] = b"\0" * len(outdata)
            offset = 0
            while offset < len(outdata):
                if not current:
                    try:
                        current = blocks.get_nowait()
                    except queue.Empty:
                        if done.is_set():
                            raise sd.CallbackStop  # PortAudio drains queued speaker frames.
                        break
                size = min(len(current), len(outdata) - offset)
                outdata[offset:offset + size] = current[:size]
                current = current[size:]
                offset += size

        try:
            stream = sd.RawOutputStream(
                device=self.output_device, samplerate=rate, channels=channels, dtype="int16",
                blocksize=max(1, rate // 50), callback=callback,
                finished_callback=playback_finished,
            )
            async for data in chunks:
                for start in range(0, len(data), 4096):
                    while blocks.full():
                        if not started:
                            stream.start()
                            started = True
                        if not stream.active:
                            raise VoiceFailure("speaker", "Speaker disconnected during playback.")
                        await asyncio.sleep(0.005)
                    piece = data[start:start + 4096]
                    blocks.put_nowait(piece)
                    if not started:
                        buffered += len(piece)
                        if buffered >= prebuffer_bytes:
                            stream.start()
                            started = True
            done.set()
            if not started:
                stream.start()
            await asyncio.wait_for(finished.wait(), timeout=5)
        except VoiceFailure:
            raise
        except Exception as error:
            raise VoiceFailure("speaker", "Speaker unavailable; check VENDI_AUDIO_OUTPUT and device permissions.") from error
        finally:
            # Synchronous close finishes BEFORE the scheduler can open another device.
            try:
                if stream is not None:
                    try:
                        stream.abort()
                    finally:
                        stream.close()
            finally:
                await chunks.aclose()

    async def capture(self, rate=16000):
        sd = sounddevice()
        loop = asyncio.get_running_loop()
        blocks = asyncio.Queue(maxsize=64)
        stream = None
        closed = False
        overflow = False

        def deliver(data, status):
            nonlocal overflow
            if closed:
                return
            if status or blocks.full():
                overflow = True
                return
            blocks.put_nowait(data)

        def callback(indata, frames, timing, status):
            loop.call_soon_threadsafe(deliver, bytes(indata), bool(status))

        try:
            stream = sd.RawInputStream(
                device=self.input_device, samplerate=rate, channels=1, dtype="int16",
                blocksize=rate // 50, callback=callback,
            )
            stream.start()
            while True:
                if overflow:
                    raise VoiceFailure("microphone", "Microphone overflow; retry or choose a different input device.")
                try:
                    yield await asyncio.wait_for(blocks.get(), timeout=1)
                except asyncio.TimeoutError:
                    if not stream.active:
                        raise VoiceFailure("microphone", "Microphone disconnected.")
        except VoiceFailure:
            raise
        except Exception as error:
            raise VoiceFailure("microphone", "Microphone unavailable; check VENDI_AUDIO_INPUT and device permissions.") from error
        finally:
            closed = True
            if stream is not None:
                try:
                    stream.abort()
                finally:
                    stream.close()


class SilentBackend:
    """Consumes real pipeline output without opening devices; used by offline demos/tests."""

    def __init__(self):
        self.playing = False
        self.listening = False

    realtime = False

    async def play(self, chunks, rate, channels=1):
        assert not self.playing and not self.listening, "Overlapping audio"
        self.playing = True
        try:
            async for _ in chunks:
                await asyncio.sleep(0)
        finally:
            self.playing = False
            await chunks.aclose()

    async def capture(self, rate=16000):
        assert not self.playing and not self.listening, "Microphone opened over speaker"
        self.listening = True
        try:
            while True:
                await asyncio.sleep(0.01)
                yield b"\0" * 640
        finally:
            self.listening = False


def wav_format(path):
    with wave.open(str(path), "rb") as audio:
        if audio.getsampwidth() != 2 or audio.getcomptype() != "NONE" or not audio.getnframes():
            raise VoiceFailure("clip", "Audio clips must be nonempty 16-bit PCM WAV files.")
        return audio.getframerate(), audio.getnchannels()


async def wav_chunks(path, duration=None):
    """Duration repeats the jingle; wall-clock pacing is handled by the real speaker."""
    with wave.open(str(path), "rb") as audio:
        remaining = int(duration * audio.getframerate()) if duration is not None else audio.getnframes()
        while remaining > 0:
            frames = min(2048, remaining)
            data = audio.readframes(frames)
            if not data:
                if duration is None:
                    break
                audio.rewind()
                data = audio.readframes(frames)
                if not data:
                    raise VoiceFailure("clip", "Jingle file is empty.")
            remaining -= len(data) // (2 * audio.getnchannels())
            yield data
            await asyncio.sleep(0)
