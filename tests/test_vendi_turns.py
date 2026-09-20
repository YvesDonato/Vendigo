"""Regression coverage for late speech, natural pauses, and premature turn cutoffs."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock

from vendi.audio.backend import SilentBackend
from vendi.audio.speech_pcm import trim_speech
from vendi.config import VoiceConfig
from vendi.conversation.agent import DemoAgent
from vendi.conversation.context import StaticContext
from vendi.errors import VoiceFailure
from vendi.events import EventType
from vendi.speech.scribe import ScribeSTT
from vendi.speech.turn import TurnProgress, is_hesitation
from vendi.speech.tts import SilentTTS
from vendi.voice import VendiVoice
from vendi.voice_state import VoiceState


class TurnProgressTests(unittest.TestCase):
    def test_idle_deadline_does_not_discard_speech_that_started_late(self):
        now = [0.0]
        activity = []
        progress = TurnProgress(8, 45, on_activity=lambda: activity.append(now[0]), clock=lambda: now[0])
        now[0] = 7.9
        progress.audio(b"\0\x10" * 1600)
        now[0] = 12
        self.assertFalse(progress.expired())
        self.assertTrue(activity)
        now[0] = 53
        with self.assertRaises(VoiceFailure):
            progress.expired()

    def test_silence_expires_but_unchanged_partials_do_not_fake_activity(self):
        now = [0]
        progress = TurnProgress(8, 45, clock=lambda: now[0])
        progress.audio(b"\0" * 3200)
        now[0] = 8
        self.assertTrue(progress.expired())
        progress.partial("I want")
        now[0] = 12
        progress.partial("I want")
        self.assertEqual(progress.last_speech, 8)

    def test_hesitations_are_not_customer_requests(self):
        for text in ("um...", "uh, um", "Hold on.", "Let me think", "Okay, so..."):
            self.assertTrue(is_hesitation(text))
        for text in ("yes", "no", "okay", "well what do you sell", "wait how much is that"):
            self.assertFalse(is_hesitation(text))


class FakeSocket:
    def __init__(self, events, first=None, keep_open=True):
        self.events = events
        self.first = first or {"message_type": "session_started"}
        self.keep_open = keep_open
        self.sent = []
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def recv(self):
        return json.dumps(self.first)

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def __aiter__(self):
        for delay, event in self.events:
            await asyncio.sleep(delay)
            yield json.dumps(event)
        if self.keep_open:
            await asyncio.Event().wait()


class RealtimeTests(unittest.IsolatedAsyncioTestCase):
    def source(self, voiced=True):
        async def stream():
            self.microphone_open = True
            count = 0
            try:
                while True:
                    yield (b"\0\x10" if voiced and count < 6 else b"\0\0") * 1600
                    count += 1
                    await asyncio.sleep(0.01)
            finally:
                self.microphone_open = False
        return stream()

    def recognizer(self, events, **kwargs):
        self.microphone_open = False
        self.socket = FakeSocket(events, **kwargs)
        self.connection_options = None
        def connect(url, **options):
            self.connection_options = (url, options)
            return self.socket
        return ScribeSTT(VoiceConfig(elevenlabs_api_key="test-key", end_silence=0.3), connect)

    async def test_waits_for_complete_sentence_past_initial_listen_timeout(self):
        stt = self.recognizer([
            (0.02, {"message_type": "partial_transcript", "text": "Can I"}),
            (0.06, {"message_type": "partial_transcript", "text": "Can I see the"}),
            (0.05, {"message_type": "committed_transcript", "text": "Can I see the menu?"}),
        ])
        result = await stt.transcribe_turn(self.source(), idle_timeout=0.04)
        self.assertEqual(result, "Can I see the menu?")
        self.assertFalse(self.microphone_open)
        self.assertTrue(self.socket.closed)
        self.assertIn("vad_silence_threshold_secs=0.3", self.connection_options[0])
        self.assertEqual(sum("previous_text" in frame for frame in self.socket.sent), 1)

    async def test_hesitation_commit_keeps_same_microphone_session_open(self):
        stt = self.recognizer([
            (0.01, {"message_type": "committed_transcript", "text": "Um..."}),
            (0.03, {"message_type": "partial_transcript", "text": "How much"}),
            (0.04, {"message_type": "committed_transcript", "text": "How much are the chips?"}),
        ])
        self.assertEqual(await stt.transcribe_turn(self.source(), 0.03), "How much are the chips?")
        self.assertFalse(self.microphone_open)

    async def test_committed_segments_are_joined_before_replying(self):
        stt = self.recognizer([
            (0.01, {"message_type": "committed_transcript", "text": "I have a question."}),
            (0.03, {"message_type": "partial_transcript", "text": "What do"}),
            (0.04, {"message_type": "committed_transcript", "text": "What do you sell?"}),
        ])
        result = await stt.transcribe_turn(self.source(), 0.03)
        self.assertEqual(result, "I have a question. What do you sell?")
        self.assertFalse(self.microphone_open)

    async def test_silence_returns_empty_without_hallucinating_a_turn(self):
        stt = self.recognizer([], keep_open=True)
        self.assertEqual(await stt.transcribe_turn(self.source(voiced=False), 0.04), "")
        self.assertFalse(self.microphone_open)

    async def test_disconnect_does_not_send_partial_text_to_agent(self):
        stt = self.recognizer([(0.01, {"message_type": "partial_transcript", "text": "I want"})], keep_open=False)
        with self.assertRaises(VoiceFailure):
            await stt.transcribe_turn(self.source(), 1)
        self.assertFalse(self.microphone_open)

    async def test_auth_errors_do_not_open_microphone_or_expose_provider_details(self):
        stt = self.recognizer([], first={"message_type": "auth_error", "error": "secret-provider-detail"})
        source = self.source()
        try:
            with self.assertRaises(VoiceFailure) as caught:
                await stt.transcribe_turn(source, 1)
            self.assertNotIn("secret-provider-detail", str(caught.exception))
            self.assertFalse(self.microphone_open)
        finally:
            await source.aclose()

    async def test_cancellation_closes_microphone_and_socket(self):
        stt = self.recognizer([], keep_open=True)
        task = asyncio.create_task(stt.transcribe_turn(self.source(), 10))
        await asyncio.sleep(0.02)
        self.assertTrue(self.microphone_open)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.microphone_open)
        self.assertTrue(self.socket.closed)

    async def test_microphone_failure_propagates_and_cancels_receiver(self):
        stt = self.recognizer([], keep_open=True)
        async def broken_source():
            raise VoiceFailure("microphone", "Microphone disconnected")
            yield b""
        with self.assertRaises(VoiceFailure) as caught:
            await stt.transcribe_turn(broken_source(), 1)
        self.assertEqual(caught.exception.component, "microphone")
        self.assertTrue(self.socket.closed)


class ConversationTimingTests(unittest.IsolatedAsyncioTestCase):
    async def test_input_recovers_once_without_reopening_every_eight_seconds(self):
        class RecoveringInput:
            max_turn_timeout = 1
            calls = 0
            idle_deadlines = []
            async def transcribe_turn(self, chunks, idle_timeout, on_activity, on_ready):
                self.calls += 1
                self.idle_deadlines.append(idle_timeout)
                on_ready()
                if self.calls == 1:
                    raise VoiceFailure("stt", "Temporary disconnect")
                return "bye"
        stt = RecoveringInput()
        events = []
        voice = VendiVoice(VoiceConfig(conversation_timeout=30, listen_timeout=8, echo_guard=0),
                           backend=SilentBackend(), tts=SilentTTS(), stt=stt,
                           agent=DemoAgent(StaticContext()), on_event=events.append)
        try:
            await voice.enter_conversation(listen=True)
            await asyncio.wait_for(voice._loop_task, 1)
            self.assertEqual(stt.calls, 2)
            self.assertTrue(all(timeout > 29 for timeout in stt.idle_deadlines))
            ended = [event for event in events if event.type == EventType.CONVERSATION_ENDED]
            self.assertEqual(ended[0].data["reason"], "customer_finished")
        finally:
            await voice.close()

    async def test_repeated_microphone_failure_stops_instead_of_looping_forever(self):
        class BrokenInput:
            max_turn_timeout = 1
            calls = 0
            async def transcribe_turn(self, chunks, **kwargs):
                self.calls += 1
                raise VoiceFailure("microphone", "Microphone disconnected")
        stt = BrokenInput()
        events = []
        voice = VendiVoice(VoiceConfig(echo_guard=0), backend=SilentBackend(), tts=SilentTTS(), stt=stt,
                           agent=DemoAgent(StaticContext()), on_event=events.append)
        try:
            await voice.enter_conversation(listen=True)
            await asyncio.wait_for(voice._loop_task, 1)
            self.assertEqual(stt.calls, 2)
            ended = [event for event in events if event.type == EventType.CONVERSATION_ENDED]
            self.assertEqual(ended[0].data["reason"], "input_failed")
        finally:
            await voice.close()

    async def test_fillers_do_not_call_gpt_or_trigger_a_reply(self):
        agent = DemoAgent(StaticContext())
        agent.respond = AsyncMock(wraps=agent.respond)
        voice = VendiVoice(VoiceConfig(), backend=SilentBackend(), tts=SilentTTS(), agent=agent)
        try:
            await voice.enter_conversation()
            await voice.handle_transcript("let me think")
            agent.respond.assert_not_called()
            self.assertEqual(voice.mode, VoiceState.CONVERSATION)
        finally:
            await voice.close()

    async def test_inactivity_timer_does_not_interrupt_active_customer_speech(self):
        class SlowCustomer:
            max_turn_timeout = 1
            async def transcribe_turn(self, chunks, idle_timeout, on_activity, on_ready):
                on_ready()
                for _ in range(8):
                    on_activity()
                    await asyncio.sleep(0.02)
                return "bye"
        events = []
        voice = VendiVoice(VoiceConfig(conversation_timeout=0.05, listen_timeout=0.025, echo_guard=0),
                           backend=SilentBackend(), tts=SilentTTS(), stt=SlowCustomer(),
                           agent=DemoAgent(StaticContext()), on_event=events.append)
        try:
            await voice.enter_conversation(listen=True)
            await asyncio.sleep(0.25)
            ended = [event for event in events if event.type == EventType.CONVERSATION_ENDED]
            self.assertEqual(len(ended), 1)
            self.assertEqual(ended[0].data["reason"], "customer_finished")
        finally:
            await voice.close()


class SpeechPaddingTests(unittest.IsolatedAsyncioTestCase):
    async def test_trims_tails_and_preserves_internal_thinking_pause(self):
        silence = b"\0\0" * 24000
        speech = b"\0\x10" * 2400
        async def source():
            yield silence
            yield speech
            yield silence[:24000]  # Half a second inside the sentence.
            yield speech
            yield silence * 2
        output = b"".join([block async for block in trim_speech(source())])
        self.assertEqual(output, silence[:4800] + speech + silence[:24000] + speech + silence[:4800])

    async def test_cancelling_trimmed_stream_closes_provider(self):
        closed = []
        async def source():
            try:
                yield b"\0\x10" * 2400
                await asyncio.sleep(10)
            finally:
                closed.append(True)
        trimmed = trim_speech(source())
        await trimmed.__anext__()
        await trimmed.aclose()
        self.assertEqual(closed, [True])

if __name__ == "__main__":
    unittest.main()
