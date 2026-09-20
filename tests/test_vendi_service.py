"""Lifecycle regressions against the real agent, without devices or providers."""

import asyncio
import unittest

from vendi.audio.backend import SilentBackend
from vendi.config import VoiceConfig
from vendi.conversation.agent import DemoAgent
from vendi.conversation.context import StaticContext
from vendi.errors import VoiceFailure
from vendi.events import EventType
from vendi.speech.tts import SilentTTS
from vendi.voice import VendiVoice
from vendi.voice_service import run_forever


class QueuedSTT:
    def __init__(self):
        self.turns = asyncio.Queue()

    async def transcribe(self, chunks):
        async for _ in chunks:
            result = await self.turns.get()
            if isinstance(result, Exception):
                raise result
            return result


class PersistentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.stt = QueuedSTT()
        self.backend = SilentBackend()
        self.voice = VendiVoice(
            VoiceConfig(echo_guard=0, conversation_timeout=0.15, listen_timeout=1),
            backend=self.backend, tts=SilentTTS(), stt=self.stt,
            agent=DemoAgent(StaticContext()), on_event=self.events.append,
        )
        self.task = asyncio.create_task(run_forever(self.voice, self.has_error))

    def has_error(self):
        return any(e.type == EventType.VOICE_ERROR for e in self.events)

    async def wait_for(self, predicate):
        async with asyncio.timeout(2):
            while not predicate():
                await asyncio.sleep(0.005)

    def count(self, event):
        return sum(e.type == event for e in self.events)

    async def asyncTearDown(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self.assertFalse(self.backend.listening)
        self.assertFalse(self.backend.playing)

    async def test_bye_keeps_listener_and_next_question_starts_new_session(self):
        await self.wait_for(lambda: self.backend.listening)
        await self.stt.turns.put('bye')
        await self.wait_for(lambda: self.count(EventType.CONVERSATION_ENDED) == 1)
        self.assertFalse(self.task.done())
        await self.stt.turns.put('Tell me a joke')
        await self.wait_for(lambda: self.count(EventType.CONVERSATION_STARTED) == 2)
        await self.wait_for(lambda: self.backend.listening)
        self.assertFalse(self.task.done())
        self.assertFalse(self.has_error())

    async def test_inactivity_keeps_listener_and_does_not_repeat_greetings(self):
        await self.wait_for(lambda: any(e.type == EventType.CONVERSATION_ENDED
                                      and e.data['reason'] == 'timeout' for e in self.events))
        await self.wait_for(lambda: self.backend.listening)
        await asyncio.sleep(0.2)
        self.assertFalse(self.task.done())
        self.assertEqual(self.count(EventType.CONVERSATION_STARTED), 1)
        await self.stt.turns.put('Hello')
        await self.wait_for(lambda: self.count(EventType.CONVERSATION_STARTED) == 2)
        self.assertFalse(self.has_error())

    async def test_device_failure_closes_audio_and_exits_for_service_restart(self):
        await self.wait_for(lambda: self.backend.listening)
        await self.stt.turns.put(VoiceFailure('microphone', 'Test disconnect'))
        with self.assertRaises(VoiceFailure):
            await asyncio.wait_for(self.task, 2)
        self.assertTrue(self.has_error())
        self.assertFalse(self.backend.listening)
        self.assertFalse(self.backend.playing)

    async def test_operator_cancellation_releases_audio(self):
        await self.wait_for(lambda: self.backend.listening)
        self.task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.task
        self.assertFalse(self.backend.listening)
        self.assertFalse(self.backend.playing)
