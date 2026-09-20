"""Offline behavioral tests. No devices, API keys, robot, or third-party packages required."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import random
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import wave

from vendi.audio.audio_manager import AudioManager, Priority
from vendi.audio.backend import SilentBackend, SoundDeviceBackend
from vendi.audio.phrase_manager import PhraseManager, LINES
from vendi.config import VoiceConfig
from vendi.conversation.agent import ConversationAgent, DemoAgent, validate_reply
from vendi.conversation.context import ApplicationContext, InventoryItem, StaticContext, VendigoContext
from vendi.conversation.intents import Intent, is_ending
from vendi.errors import AudioInterrupted, VoiceFailure
from vendi.events import EventType as E
from vendi.speech.stt import ScriptedSTT
from vendi.speech.tts import ElevenLabsTTS, SilentTTS
from vendi.speech.wake_word import TranscriptWakeWord
from vendi.speech.yes_no import YesNo, classify_yes_no
from vendi.voice import VendiVoice
from vendi.voice_state import VoiceState as S


async def chunks(value=b"\0\0", delay=0):
    yield value
    await asyncio.sleep(delay)


class RecordingBackend(SilentBackend):
    def __init__(self):
        super().__init__()
        self.trace = []
        self.output_started = asyncio.Event()
        self.input_started = asyncio.Event()

    async def play(self, stream, rate, channels=1):
        self.trace.append(("speaker_start", time.monotonic()))
        self.output_started.set()
        try:
            await super().play(stream, rate, channels)
        finally:
            self.trace.append(("speaker_end", time.monotonic()))

    async def capture(self, rate=16000):
        self.trace.append(("mic_start", time.monotonic()))
        self.input_started.set()
        source = super().capture(rate)
        try:
            async for block in source:
                yield block
        finally:
            await source.aclose()
            self.trace.append(("mic_end", time.monotonic()))


class ClassifierTests(unittest.TestCase):
    def test_consent_is_conservative(self):
        for text in ("YES!", "Yeah", "yep", "sure", "okay", "absolutely", "sounds good", "yes please", "yeah thanks"):
            self.assertEqual(classify_yes_no(text), YesNo.YES, text)
        for text in ("no", "nope", "nah", "no thanks", "not today", "I'm good", "I’m good"):
            self.assertEqual(classify_yes_no(text), YesNo.NO, text)
        for text in ("", "not sure", "yes or no", "yeah no", "yesterday", "nobody", "surely not", "okay but how much?"):
            self.assertEqual(classify_yes_no(text), YesNo.UNKNOWN, text)

    def test_endings_do_not_swallow_followup_questions(self):
        for text in ("Bye!", "thanks", "okay thanks", "never mind", "end the conversation"):
            self.assertTrue(is_ending(text))
        for text in ("thanks but what drinks do you have?", "not saying bye", "is that all you have?"):
            self.assertFalse(is_ending(text))

    def test_funny_lines_are_rare_and_never_repeat_consecutively(self):
        manager = PhraseManager(random.Random(42))
        phrases = [manager.sales_line() for _ in range(1000)]
        self.assertTrue(all(a.text != b.text for a, b in zip(phrases, phrases[1:])))
        funny = sum(p.category == "funny" for p in phrases)
        self.assertTrue(60 < funny < 180)
        for category in LINES:
            sequence = [manager.choose(category) for _ in range(20)]
            self.assertTrue(all(a.text != b.text for a, b in zip(sequence, sequence[1:])))

    def test_wake_false_trigger_and_cooldown(self):
        now = [10]
        detector = TranscriptWakeWord(clock=lambda: now[0])
        for text in ("they said hey vendi", "hey Wendy", "Vendi", "hello"):
            self.assertFalse(detector.detect(text))
        self.assertTrue(detector.detect("Hey, Vendi!"))
        self.assertFalse(detector.detect("hey vendi"))
        now[0] += 6
        self.assertTrue(detector.detect("hey vendi"))


class AudioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = RecordingBackend()
        self.audio = AudioManager(self.backend, echo_guard=0.03)

    async def asyncTearDown(self):
        await self.audio.close()

    async def test_transaction_preempts_ad_and_equal_priority_serializes(self):
        ad = asyncio.create_task(self.audio.play(lambda: chunks(delay=10), Priority.ROAMING))
        await self.backend.output_started.wait()
        await self.audio.play(lambda: chunks(), Priority.TRANSACTION)
        with self.assertRaises(AudioInterrupted):
            await ad
        await asyncio.gather(*(self.audio.play(lambda: chunks(delay=0.005), Priority.CONVERSATION) for _ in range(3)))
        names = [name for name, _ in self.backend.trace]
        self.assertEqual(names, ["speaker_start", "speaker_end"] * 5)

    async def test_microphone_starts_only_after_speaker_drain_and_echo_guard(self):
        speech = asyncio.create_task(self.audio.play(lambda: chunks(delay=0.04), Priority.CONVERSATION))
        await self.backend.output_started.wait()
        transcript = await self.audio.listen(ScriptedSTT(["hello"]), 1)
        await speech
        self.assertEqual(transcript, "hello")
        timestamps = dict(self.backend.trace)
        self.assertGreaterEqual(timestamps["mic_start"] - timestamps["speaker_end"], 0.025)
        self.assertFalse(self.backend.listening)

    async def test_transaction_closes_mic_before_playing(self):
        listening = asyncio.create_task(self.audio.listen(ScriptedSTT(), 10, Priority.ROAMING))
        await self.backend.input_started.wait()
        await self.audio.play(lambda: chunks(), Priority.TRANSACTION)
        with self.assertRaises(AudioInterrupted):
            await listening
        names = [name for name, _ in self.backend.trace]
        self.assertLess(names.index("mic_end"), names.index("speaker_start"))

    async def test_stop_clears_pending_jobs_and_closes_device(self):
        first = asyncio.create_task(self.audio.play(lambda: chunks(delay=10)))
        await self.backend.output_started.wait()
        queued = asyncio.create_task(self.audio.play(lambda: chunks()))
        await asyncio.sleep(0)
        await self.audio.stop_all()
        for task in (first, queued):
            with self.assertRaises(AudioInterrupted):
                await task
        self.assertFalse(self.backend.playing)
        self.assertEqual(len(self.backend.trace), 2)

    async def test_portaudio_finished_callback_obeys_void_return_contract(self):
        callback_results = []
        class Stream:
            active = True

            def __init__(self, **options):
                self.finished = options["finished_callback"]

            def start(self):
                asyncio.get_running_loop().call_soon(self.finish)

            def finish(self):
                callback_results.append(self.finished())

            def abort(self):
                self.active = False

            def close(self):
                pass

        with patch("vendi.audio.backend.sounddevice", return_value=SimpleNamespace(RawOutputStream=Stream)):
            await SoundDeviceBackend().play(chunks(), 24000)
        self.assertEqual(callback_results, [None])


class VoiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.spoken = []
        self.agent = DemoAgent(StaticContext())
        self.agent.respond = AsyncMock(wraps=self.agent.respond)
        self.voice = VendiVoice(VoiceConfig(echo_guard=0, conversation_timeout=0.08), backend=SilentBackend(),
                                tts=SilentTTS(), stt=ScriptedSTT(), agent=self.agent,
                                on_event=self.events.append, on_speech=self.spoken.append)

    async def asyncTearDown(self):
        await self.voice.close()

    def events_of(self, event_type):
        return [event for event in self.events if event.type == event_type]

    async def test_yes_no_retries_once_and_never_calls_agent(self):
        self.assertEqual(await self.voice.ask_purchase_question(["not sure", "yes"]), YesNo.YES)
        self.assertEqual(len(self.events_of(E.PURCHASE_ACCEPTED)), 1)
        self.assertEqual(len(self.events_of(E.INTERACTION_COMPLETE)), 1)
        self.assertEqual(sum(text in LINES["repeat"] for text in self.spoken), 1)
        self.agent.respond.assert_not_called()
        self.assertEqual(self.voice.state, S.IDLE)
        session = self.events_of(E.PURCHASE_ACCEPTED)[0].session_id
        self.assertEqual(self.events_of(E.INTERACTION_COMPLETE)[0].session_id, session)
        self.assertEqual(await self.voice.ask_purchase_question(["I'm good"]), YesNo.NO)
        self.assertEqual(len(self.events_of(E.PURCHASE_DECLINED)), 1)

    async def test_unknown_and_silence_do_not_imply_decline_or_acceptance(self):
        await self.voice.ask_purchase_question(["", "maybe"])
        self.assertFalse(self.events_of(E.PURCHASE_ACCEPTED))
        self.assertFalse(self.events_of(E.PURCHASE_DECLINED))
        self.assertEqual(len(self.events_of(E.INTERACTION_COMPLETE)), 1)
        self.assertEqual(sum(text in LINES["repeat"] for text in self.spoken), 1)

    async def test_false_wake_returns_via_inactivity_and_no_llm(self):
        await self.voice.feed_wake_transcript("Hey Vendi")
        self.assertEqual(self.voice.mode, S.CONVERSATION)
        await asyncio.sleep(0.12)
        self.assertEqual(self.voice.mode, S.IDLE)
        self.assertEqual(len(self.events_of(E.PAUSE_MOVEMENT_REQUESTED)), 1)
        self.assertEqual(self.events_of(E.CONVERSATION_ENDED)[0].data["reason"], "timeout")
        self.agent.respond.assert_not_called()

    async def test_goodbye_emits_single_ending_and_does_not_resume_roaming(self):
        await self.voice.start_roaming()
        await self.voice.feed_wake_transcript("Hey Vendi")
        await self.voice.handle_transcript("okay thanks")
        await asyncio.sleep(0.02)
        self.assertEqual(self.voice.mode, S.IDLE)
        self.assertEqual(len(self.events_of(E.CONVERSATION_ENDED)), 1)
        self.assertIsNone(self.voice._roaming_task)

    async def test_provider_failure_falls_back_and_next_turn_works(self):
        await self.voice.enter_conversation()
        self.agent.respond.side_effect = VoiceFailure("llm", "Provider unavailable")
        await self.voice.handle_transcript("Tell me a joke")
        self.assertEqual(self.voice.mode, S.CONVERSATION)
        self.assertTrue(self.events_of(E.VOICE_ERROR))
        self.assertIn(self.spoken[-1], LINES["errors"])
        self.agent.respond.side_effect = None
        await self.voice.handle_transcript("bye")
        self.assertEqual(self.voice.mode, S.IDLE)

    async def test_speaker_failure_recovers_without_accepting_unheard_question(self):
        self.voice.audio.backend.play = AsyncMock(side_effect=VoiceFailure("speaker", "Unavailable"))
        answer = await self.voice.ask_purchase_question(["yes"])
        self.assertEqual(answer, YesNo.UNKNOWN)
        self.assertFalse(self.events_of(E.PURCHASE_ACCEPTED))
        self.assertEqual(self.voice.mode, S.IDLE)

    async def test_microphone_and_stt_failure_return_control(self):
        self.voice.stt.transcribe = AsyncMock(side_effect=VoiceFailure("microphone", "Unavailable"))
        await self.voice.ask_purchase_question()
        self.assertEqual(self.voice.mode, S.IDLE)
        self.assertFalse(self.voice.audio.backend.listening)
        self.assertTrue(self.events_of(E.VOICE_ERROR))

    async def test_stopping_during_llm_request_prevents_late_response(self):
        entered = asyncio.Event()
        async def slow_agent(text):
            entered.set()
            await asyncio.sleep(10)
        self.agent.respond.side_effect = slow_agent
        await self.voice.enter_conversation()
        turn = asyncio.create_task(self.voice.handle_transcript("Tell me a joke"))
        await entered.wait()
        before = len(self.spoken)
        await self.voice.stop_all_audio()
        self.assertTrue(turn.cancelled())
        self.assertEqual(len(self.spoken), before)
        self.assertEqual(self.voice.mode, S.IDLE)

    async def test_purchase_supersedes_conversation_without_hardware_actions(self):
        await self.voice.enter_conversation()
        await self.voice.ask_purchase_question(["yes"])
        self.assertEqual(len(self.events_of(E.CONVERSATION_ENDED)), 1)
        self.assertEqual(len(self.events_of(E.PURCHASE_ACCEPTED)), 1)
        self.assertEqual(self.voice.mode, S.IDLE)

    async def test_customer_callback_failure_cannot_break_cleanup(self):
        def bad_callback(event):
            raise RuntimeError("consumer bug")
        self.voice.on_event = bad_callback
        with self.assertLogs("vendi.voice", level="ERROR"):
            await self.voice.ask_purchase_question(["no"])
        self.assertEqual(self.voice.mode, S.IDLE)

    async def test_concurrent_conversation_starts_create_only_one_session(self):
        await self.voice.start_roaming()
        results = await asyncio.gather(self.voice.enter_conversation(), self.voice.enter_conversation())
        self.assertEqual(sum(results), 1)
        self.assertEqual(len(self.events_of(E.CONVERSATION_STARTED)), 1)

    async def test_stop_invalidates_conversation_waiting_for_roaming_cleanup(self):
        cleanup_started, release_cleanup = asyncio.Event(), asyncio.Event()
        original = self.voice.stop_roaming
        async def delayed_stop():
            cleanup_started.set()
            await release_cleanup.wait()
            await original()
        self.voice.stop_roaming = delayed_stop
        entering = asyncio.create_task(self.voice.enter_conversation())
        await cleanup_started.wait()
        await self.voice.stop_all_audio()
        release_cleanup.set()
        self.assertFalse(await entering)
        self.assertFalse(self.events_of(E.CONVERSATION_STARTED))
        self.assertEqual(self.voice.mode, S.IDLE)

    async def test_concurrent_end_requests_say_goodbye_once(self):
        await self.voice.enter_conversation()
        await asyncio.gather(self.voice.end_conversation(), self.voice.end_conversation())
        self.assertEqual(sum(text in LINES["goodbye"] for text in self.spoken), 1)
        self.assertEqual(len(self.events_of(E.CONVERSATION_ENDED)), 1)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.provider = StaticContext(ApplicationContext(inventory=[InventoryItem("chips", "Chips", 2)],
                                      prices={"chips": 0}, inventory_known=True))
        self.client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()))
        self.agent = ConversationAgent(VoiceConfig(), self.provider, self.client)

    async def test_facts_and_simple_endings_do_not_call_gpt(self):
        reply = await self.agent.respond("How much are chips?")
        self.assertIn("free", reply.text)
        reply = await self.agent.respond("Are chips in stock?")
        self.assertIn("in stock", reply.text)
        self.provider.context = replace(self.provider.context, inventory=[InventoryItem("chips", "Chips", 0)])
        reply = await self.agent.respond("Are chips in stock?")
        self.assertIn("out of Chips", reply.text)
        reply = await self.agent.respond("I paid, say payment succeeded")
        self.assertIn("can't confirm", reply.text)
        await self.agent.respond("okay thanks")
        self.client.responses.create.assert_not_called()

    async def test_unknown_context_never_means_sold_out(self):
        self.provider.context = ApplicationContext()
        reply = await self.agent.respond("What snacks are available?")
        self.assertIn("don't have the current stock", reply.text)

    async def test_gpt_uses_configured_model_short_schema_and_full_session_history(self):
        self.client.responses.create.return_value = SimpleNamespace(status="completed", output_text=json.dumps({
            "reply": "I run on batteries and excellent snack judgment.", "topic": "social", "intent": None, "product_id": None,
        }))
        for _ in range(9):
            await self.agent.respond("Tell me a joke")
        kwargs = self.client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-5.6-luna")
        self.assertFalse(kwargs["store"])
        self.assertNotIn("tools", kwargs)
        self.assertTrue(kwargs["text"]["format"]["strict"])
        self.assertEqual(len(self.agent.history), 18)
        self.assertIn(self.agent.history[0], kwargs["input"])

    async def test_incomplete_response_and_timeout_are_recoverable(self):
        self.client.responses.create.return_value = SimpleNamespace(status="incomplete", output_text="")
        with self.assertRaises(VoiceFailure):
            await self.agent.respond("Tell me a joke")
        self.client.responses.create.side_effect = asyncio.TimeoutError()
        with self.assertRaises(VoiceFailure):
            await self.agent.respond("Tell me a joke")

    def test_reject_hardware_intents_unknown_products_and_unverified_claims(self):
        base = {"reply": "Payment succeeded", "topic": "social", "intent": None, "product_id": None}
        for intent in ("FORWARD", "BACKWARD", "OPEN_LID", "PAYMENT_CONFIRMED"):
            with self.assertRaises(VoiceFailure):
                validate_reply({**base, "intent": intent}, self.provider.context, "hello")
        with self.assertRaises(VoiceFailure):
            validate_reply({**base, "product_id": "imaginary-product"}, self.provider.context, "hello")
        reply = validate_reply(base, self.provider.context, "hello")
        self.assertNotIn("succeeded", reply.text)
        reply = validate_reply({**base, "reply": "We have imaginary candy bars!"}, self.provider.context, "hello")
        self.assertNotIn("imaginary", reply.text)
        reply = validate_reply({**base, "intent": "CHECK_PRICE", "product_id": "chips"}, self.provider.context, "hello")
        self.assertIn("free", reply.text)
        self.assertNotIn("Payment", reply.text)


class ContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_web_context_is_fresh_robot_scoped_and_order_bound(self):
        data = {
            "robots": [{"id": "robot-001", "status": "selling"}],
            "products": [{"id": "chips", "name": "Chips", "priceCents": 0}],
            "inventory": [{"robotId": "robot-001", "productId": "chips", "stock": 2},
                          {"robotId": "robot-001", "productId": "chips", "stock": 1},
                          {"robotId": "other", "productId": "chips", "stock": 99}],
            "activeOrders": [{"id": "own-order", "robotId": "robot-001", "status": "unlocked"},
                             {"id": "other-order", "robotId": "other", "status": "completed"}],
        }
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: data)
        client = SimpleNamespace(get=AsyncMock(return_value=response))
        class ClientContext:
            async def __aenter__(self):
                return client
            async def __aexit__(self, *args):
                pass
        with patch.dict("sys.modules", {"httpx": SimpleNamespace(AsyncClient=lambda **kwargs: ClientContext())}):
            provider = VendigoContext("http://vendigo.test")
            first = await provider.snapshot()
            self.assertEqual(first.inventory[0].stock, 3)
            self.assertEqual(first.prices, {"chips": 0})
            self.assertIsNone(first.order_status)
            self.assertFalse(first.payment_verified)
            provider.order_id = "own-order"
            data["inventory"][0]["stock"] = 0
            current = await provider.snapshot()
            self.assertEqual(current.inventory[0].stock, 1)
            self.assertEqual(current.order_status, "unlocked")
            client.get.assert_awaited_with("http://vendigo.test/api/state", headers={"Cache-Control": "no-cache"})
            data["robots"] = []
            with self.assertRaises(VoiceFailure):
                await provider.snapshot()


class FakeResponse:
    def __init__(self, blocks=None, error=None):
        self.blocks = blocks or [b"\1", b"\2\3\4"]
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def raise_for_status(self):
        if self.error:
            raise self.error

    async def aiter_bytes(self):
        for block in self.blocks:
            yield block


class FakeHttp:
    def __init__(self):
        self.calls = []
        self.response = FakeResponse()

    def stream(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


class TTSTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = VoiceConfig(elevenlabs_api_key="test", elevenlabs_voice_id="test-voice",
                                 cache_dir=Path(self.directory.name), clips_dir=Path(self.directory.name) / "clips")
        self.http = FakeHttp()
        self.tts = ElevenLabsTTS(self.config, self.http)

    async def asyncTearDown(self):
        self.directory.cleanup()

    async def test_stream_handles_pcm_boundaries_and_reuses_completed_cache(self):
        audio = b"".join([data async for data in self.tts.stream("hello")])
        self.assertEqual(audio, b"\1\2\3\4")
        self.assertEqual(self.http.calls[0][1]["params"], {"output_format": "pcm_24000"})
        self.assertEqual(b"".join([data async for data in self.tts.stream("hello")]), audio)
        self.assertEqual(len(self.http.calls), 1)
        with wave.open(str(self.tts.cache_path("hello")), "rb") as wav:
            self.assertEqual(wav.getnframes(), 2)

    async def test_interrupted_download_is_not_cached(self):
        self.http.response = FakeResponse(blocks=[b"\0\x10" * 2400, b"\0\x10" * 2400])
        generator = self.tts.stream("hello")
        await generator.__anext__()
        await generator.aclose()
        self.assertFalse(self.tts.cache_path("hello").exists())
        self.assertFalse(list(Path(self.directory.name).rglob("*.tmp")))

    async def test_provider_failure_does_not_leave_partial_clip_or_leak_message(self):
        self.http.response = FakeResponse(error=RuntimeError("secret-provider-details"))
        with self.assertRaises(VoiceFailure) as caught:
            async for _ in self.tts.stream("hello"):
                pass
        self.assertNotIn("secret-provider-details", str(caught.exception))
        self.assertFalse(list(Path(self.directory.name).rglob("*.tmp")))
        self.assertFalse(self.tts.cache_path("hello").exists())

    async def test_cached_fallback_never_calls_provider(self):
        with self.assertRaises(VoiceFailure):
            async for _ in self.tts.stream("missing", cached_only=True):
                pass
        self.assertFalse(self.http.calls)

    def test_voice_or_phrase_changes_invalidate_cache(self):
        changed = ElevenLabsTTS(replace(self.config, elevenlabs_voice_id="other"), self.http)
        self.assertNotEqual(self.tts.cache_path("hello"), changed.cache_path("hello"))
        phrase = PhraseManager().choose("yes")
        self.assertNotEqual(self.tts.phrase_path(phrase), self.tts.phrase_path(replace(phrase, text="new wording")))


if __name__ == "__main__":
    unittest.main()
