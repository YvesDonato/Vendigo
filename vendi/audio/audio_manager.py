"""Priority arbitration for speech, music AND mic; all share one exclusive worker."""

import asyncio
from dataclasses import dataclass, field
from enum import IntEnum
import heapq
import itertools
import time

from vendi.audio.backend import wav_chunks, wav_format
from vendi.errors import AudioInterrupted, VoiceFailure
from vendi.voice_state import VoiceState


class Priority(IntEnum):
    TRANSACTION = 1
    CONVERSATION = 2
    CALLOUT = 3
    ROAMING = 4
    JINGLE = 5


@dataclass(order=True)
class Job:
    priority: int
    sequence: int
    operation: object = field(compare=False)
    activity: object = field(compare=False)
    result: object = field(compare=False)


class AudioManager:
    def __init__(self, backend, on_activity=lambda state: None, echo_guard=0.2):
        self.backend = backend
        self.on_activity = on_activity
        self.echo_guard = echo_guard
        self._queue = []
        self._sequence = itertools.count()
        self._worker = None
        self._active = None
        self._active_job = None
        self._last_output = float("-inf")
        self._closed = False

    async def _submit(self, operation, priority, activity):
        if self._closed:
            raise AudioInterrupted("Audio manager is closed")
        future = asyncio.get_running_loop().create_future()
        job = Job(priority, next(self._sequence), operation, activity, future)
        heapq.heappush(self._queue, job)
        if self._active and priority < self._active_job.priority:
            self._active.cancel()
        if self._worker is None:
            self._worker = asyncio.create_task(self._drain())
        try:
            return await future
        except asyncio.CancelledError:
            future.cancel()
            if self._active_job is job and self._active:
                self._active.cancel()
            raise

    async def _drain(self):
        try:
            while self._queue:
                job = heapq.heappop(self._queue)
                if job.result.done():
                    continue
                self._active_job = job
                self.on_activity(job.activity)
                self._active = asyncio.create_task(job.operation())
                try:
                    result = await self._active
                    if not job.result.done():
                        job.result.set_result(result)
                except asyncio.CancelledError:
                    if not job.result.done():
                        job.result.set_exception(AudioInterrupted("Superseded or stopped"))
                except Exception as error:
                    if not job.result.done():
                        job.result.set_exception(error)
                finally:
                    if job.activity == VoiceState.SPEAKING or job.priority == Priority.JINGLE:
                        self._last_output = time.monotonic()
                    self._active = self._active_job = None
                    self.on_activity(None)
        finally:
            self._worker = None

    async def play(self, chunks_factory, priority=Priority.CONVERSATION, rate=24000, channels=1):
        async def output():
            await self.backend.play(chunks_factory(), rate, channels)
        await self._submit(output, priority, VoiceState.SPEAKING)

    async def play_clip(self, path, priority=Priority.CONVERSATION):
        rate, channels = wav_format(path)
        await self.play(lambda: wav_chunks(path), priority, rate, channels)

    async def play_jingle(self, path, duration):
        rate, channels = wav_format(path)
        await self._submit(lambda: self.backend.play(wav_chunks(path, duration), rate, channels),
                           Priority.JINGLE, None)

    async def listen(self, stt, timeout, priority=Priority.CONVERSATION, on_activity=lambda: None, on_ready=lambda: None):
        async def input_turn():
            # Guard starts after PortAudio drains/closes, never after a network audio packet.
            await asyncio.sleep(max(0, self.echo_guard - (time.monotonic() - self._last_output)))
            chunks = self.backend.capture(16000)
            try:
                if hasattr(stt, "transcribe_turn"):
                    # timeout is time to START talking. A started utterance gets its own budget.
                    return await asyncio.wait_for(
                        stt.transcribe_turn(chunks, idle_timeout=timeout, on_activity=on_activity, on_ready=on_ready),
                        timeout=timeout + stt.max_turn_timeout,
                    )
                on_ready()
                return await asyncio.wait_for(stt.transcribe(chunks), timeout=timeout)
            except asyncio.TimeoutError:
                if hasattr(stt, "transcribe_turn"):
                    raise VoiceFailure("stt", "Speech recognition stalled; please try that sentence again.")
                return ""
            finally:
                await chunks.aclose()  # Fresh input stream next turn; no speaker-tail buffer.
        return await self._submit(input_turn, priority, VoiceState.LISTENING)

    async def stop_all(self):
        queue, self._queue = self._queue, []
        for job in queue:
            if not job.result.done():
                job.result.set_exception(AudioInterrupted("Stopped"))
        worker = self._worker
        if self._active:
            self._active.cancel()
        if worker:
            await asyncio.shield(worker)

    async def close(self):
        self._closed = True
        await self.stop_all()
