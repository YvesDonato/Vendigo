"""Gate contract and real voice integration, with no network/audio devices."""

import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from vendi.audio.backend import SilentBackend
from vendi.config import VoiceConfig
from vendi.conversation.agent import ConversationAgent
from vendi.conversation.context import ApplicationContext, InventoryItem, StaticContext
from vendi.events import EventType
from vendi.shopping_gate import ShoppingIntentGate
from vendi.speech.stt import ScriptedSTT
from vendi.speech.tts import SilentTTS
from vendi.voice import VendiVoice
from vendi.voice_state import VoiceState


def model_result(intent="shopping", confidence=0.98):
    return SimpleNamespace(status="completed", output_text=json.dumps({
        "intent": intent, "confidence": confidence,
    }))


def session_input(request):
    return json.loads(request["input"][0]["content"].split(": ", 1)[1])


class ShoppingGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 100.0
        self.create = AsyncMock(return_value=model_result())
        self.client = SimpleNamespace(responses=SimpleNamespace(create=self.create))
        self.gate = ShoppingIntentGate(VoiceConfig(shopping_gate_timeout=0.02), self.client,
                                       clock=lambda: self.now)

    async def test_wake_variants_bypass_provider_and_word_boundaries_avoid_names(self):
        for text in ("Vendi", "Vendigo, what do you have?", "Hey Vendy!", "Vendie?",
                     "Hello Vendee", "Vendygo", "Vendego", "vend-ee-go", "vend e go",
                     "Can you help me, Vendi?"):
            self.assertTrue((await self.gate.classify(text)).allowed, text)
        self.create.assert_not_called()
        self.create.return_value = model_result("ignore", 0.99)
        for text in ("Hey Wendy", "vendigophile", "vending machine learning", "a souvenir"):
            self.assertFalse((await self.gate.classify(text)).allowed, text)
        self.assertEqual(self.create.await_count, 4)

    async def test_threshold_and_invalid_outputs_fail_closed(self):
        for intent, confidence, allowed in (("shopping", 0.98, True), ("shopping", 0.90, True),
                                            ("shopping", 0.89, False), ("ignore", 0.99, False),
                                            ("ignore", 0.1, False)):
            self.create.return_value = model_result(intent, confidence)
            self.assertEqual((await self.gate.classify("How much is Coke?")).allowed, allowed)
        for raw in (None, [], {}, {"intent": "shopping", "confidence": True},
                    {"intent": "shopping", "confidence": "1"},
                    {"intent": "shopping", "confidence": float("nan")},
                    {"intent": "shopping", "confidence": float("inf")},
                    {"intent": "shopping", "confidence": 1.1},
                    {"intent": "shopping", "confidence": -0.1},
                    {"intent": "other", "confidence": 1},
                    {"intent": "shopping", "confidence": 1, "reply": "hi"}):
            self.create.return_value = SimpleNamespace(status="completed", output_text=json.dumps(raw))
            self.assertFalse((await self.gate.classify("Do you have Coke?")).allowed, raw)
        for status, output in (("incomplete", model_result().output_text), ("completed", "not JSON")):
            self.create.return_value = SimpleNamespace(status=status, output_text=output)
            self.assertFalse((await self.gate.classify("Do you have Coke?")).allowed)

    async def test_explicit_shop_entry_questions_work_without_product_context(self):
        for text in ("Which one do you recommend?", "What would you recommend?",
                     "How do I buy this?", "How can I buy this?", "How do I buy something?"):
            self.assertTrue((await self.gate.classify(text)).allowed, text)
        self.create.assert_not_called()
        self.create.return_value = model_result("ignore", 0.99)
        for text in ("Alex, which one do you recommend?", "My friend asked how do I buy this",
                     "How do I buy this domain for the backend?", "Which one do you recommend for coding?"):
            self.assertFalse((await self.gate.classify(text)).allowed, text)
        self.assertEqual(self.create.await_count, 4)

    async def test_timeout_failure_and_missing_key_are_silent_without_retries(self):
        self.create.side_effect = RuntimeError("secret-provider-details")
        with self.assertLogs("vendi.shopping_gate", level="DEBUG") as logs:
            self.assertFalse((await self.gate.classify("Do you have Coke?")).allowed)
        self.assertNotIn("secret-provider-details", " ".join(logs.output))
        self.assertEqual(self.create.await_count, 1)
        async def stalled(**kwargs):
            await asyncio.Event().wait()
        self.create.side_effect = stalled
        self.assertFalse((await self.gate.classify("Do you have Coke?")).allowed)
        self.assertFalse((await ShoppingIntentGate(VoiceConfig()).classify("Do you have Coke?")).allowed)

    async def test_goodbye_passes_only_with_active_context(self):
        self.create.return_value = model_result("ignore", 0.99)
        self.assertFalse((await self.gate.classify("Bye")).allowed)
        self.create.reset_mock()
        self.gate.activate()
        for text in ("Bye", "Okay thanks", "Never mind"):
            self.assertTrue((await self.gate.classify(text)).allowed)
        self.create.assert_not_called()
        self.now += 30
        self.assertFalse((await self.gate.classify("Bye")).allowed)

    async def test_noisy_transcripts_do_not_call_classifier(self):
        for text in ("", " ", "...", "123", "Um...", "uh um", "Okay, so...", "x" * 2001):
            self.assertFalse((await self.gate.classify(text)).allowed)
        self.create.assert_not_called()

    async def test_session_expires_exactly_30_seconds_and_ignore_never_refreshes_it(self):
        self.gate.activate()
        self.now += 29.9
        self.assertTrue(self.gate.active)
        self.create.return_value = model_result("ignore", 0.99)
        await self.gate.classify("Did you push the code?")
        self.now += 0.1
        self.assertFalse(self.gate.active)
        self.gate.activate()
        self.assertEqual(self.gate.remaining, 30)
        self.gate.reset()
        self.assertFalse(self.gate.active)

    async def test_only_active_recent_context_is_sent_and_no_tools_or_inventory(self):
        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": "Coke " * 150}
                   for i in range(12)]
        await self.gate.classify("What about the blue one?", history)
        request = self.create.call_args.kwargs
        self.assertFalse(session_input(request)["shopping_active"])
        self.assertEqual(session_input(request)["recent_conversation"], [])
        self.gate.activate()
        await self.gate.classify("What about the blue one?", history)
        request = self.create.call_args.kwargs
        context = session_input(request)
        self.assertTrue(context["shopping_active"])
        self.assertEqual(len(context["recent_conversation"]), 6)
        self.assertTrue(all(len(item["content"]) <= 500 for item in context["recent_conversation"]))
        self.assertEqual(set(context), {"shopping_active", "recent_conversation"})
        self.assertEqual(request["input"][-1], {"role": "user", "content": "What about the blue one?"})
        self.assertNotIn("tools", request)
        self.assertFalse(request["store"])
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertEqual(request["max_output_tokens"], 80)

    async def test_late_contextual_classification_cannot_revive_expired_session(self):
        self.gate.activate()
        async def late(**kwargs):
            self.now += 31
            return model_result()
        self.create.side_effect = late
        self.assertFalse((await self.gate.classify("I'll take it")).allowed)
        self.assertFalse(self.gate.active)

    async def test_short_followups_require_active_history_and_shopping_classification(self):
        history = [{"role": "user", "content": "What drinks do you have?"},
                   {"role": "assistant", "content": "Coke and Gatorade are in stock."}]
        self.create.return_value = model_result("shopping", 0.85)
        self.assertFalse((await self.gate.classify("What about that one?", history)).allowed)
        self.gate.activate()
        self.assertFalse((await self.gate.classify("What about that one?")).allowed)
        self.assertTrue((await self.gate.classify("What about that one?", history)).allowed)
        self.assertTrue((await self.gate.classify("Do you have another?", history)).allowed)
        self.assertFalse((await self.gate.classify("Did you push the code?", history)).allowed)
        self.create.return_value = model_result("ignore", 0.99)
        self.assertFalse((await self.gate.classify("What about that one?", history)).allowed)
        self.create.return_value = model_result("shopping", 0.84)
        self.assertFalse((await self.gate.classify("What about that one?", history)).allowed)

    async def test_cancellation_propagates(self):
        self.create.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await self.gate.classify("Do you have Coke?")


class GatedVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 100.0
        self.events, self.spoken = [], []
        self.create = AsyncMock(return_value=model_result())
        self.gate = ShoppingIntentGate(VoiceConfig(),
            SimpleNamespace(responses=SimpleNamespace(create=self.create)), clock=lambda: self.now)
        self.context = StaticContext(ApplicationContext(
            inventory=[InventoryItem("coke", "Coke", 4)], prices={"coke": 100}, inventory_known=True))
        self.context.snapshot = AsyncMock(wraps=self.context.snapshot)
        self.agent = ConversationAgent(VoiceConfig(), self.context)
        self.agent.respond = AsyncMock(wraps=self.agent.respond)
        self.tts = SilentTTS()
        self.voice = VendiVoice(VoiceConfig(echo_guard=0), backend=SilentBackend(), tts=self.tts,
            stt=ScriptedSTT(), agent=self.agent, shopping_gate=self.gate,
            on_event=self.events.append, on_speech=self.spoken.append)

    async def asyncTearDown(self):
        await self.voice.close()

    async def test_ignore_never_reaches_agent_inventory_history_tts_or_ui(self):
        self.create.return_value = model_result("ignore", 0.99)
        for text in ("Did you finish the backend?", "Where's the bathroom?", "That presentation was crazy.",
                     "I'm going upstairs.", "What time does judging start?", "Bro come over here."):
            self.assertIsNone(await self.voice.handle_microphone_transcript(text))
        self.agent.respond.assert_not_called()
        self.context.snapshot.assert_not_called()
        self.assertEqual(self.agent.history, [])
        self.assertEqual(self.spoken, [])
        self.assertEqual(self.events, [])
        self.assertEqual(self.voice.mode, VoiceState.IDLE)

    async def test_accepted_turns_fetch_fresh_inventory_and_followups_keep_context(self):
        await self.voice.handle_microphone_transcript("Do you have Coke?")
        self.assertIn("4 left", self.spoken[-1])
        self.context.context = ApplicationContext(
            inventory=[InventoryItem("coke", "Coke", 2)], prices={"coke": 250}, inventory_known=True)
        self.now += 20
        await self.voice.handle_microphone_transcript("How much?")
        self.assertIn("2.50", self.spoken[-1])
        self.assertEqual(self.gate.remaining, 30)
        self.assertEqual(self.context.snapshot.await_count, 2)
        data = session_input(self.create.call_args.kwargs)
        self.assertTrue(data["shopping_active"])
        self.assertIn("Do you have Coke?", str(data["recent_conversation"]))
        self.create.return_value = model_result("ignore", 0.99)
        self.now += 20
        previous_history, previous_speech = list(self.agent.history), list(self.spoken)
        await self.voice.handle_microphone_transcript("Did you push the code?")
        self.assertEqual(self.agent.history, previous_history)
        self.assertEqual(self.spoken, previous_speech)
        self.assertEqual(self.gate.remaining, 10)

    async def test_expiry_silently_clears_context_and_wake_reactivates(self):
        await self.voice.handle_microphone_transcript("Do you have Coke?")
        self.now += 30
        self.create.return_value = model_result("ignore", 0.99)
        spoken = list(self.spoken)
        await self.voice.handle_microphone_transcript("What about that one?")
        self.assertEqual(self.spoken, spoken)
        self.assertEqual(self.agent.history, [])
        self.assertEqual(self.voice.mode, VoiceState.IDLE)
        data = session_input(self.create.call_args.kwargs)
        self.assertFalse(data["shopping_active"])
        await self.voice.handle_microphone_transcript("Vendi, do you have Coke?")
        self.assertTrue(self.gate.active)
        self.assertEqual(self.voice.mode, VoiceState.CONVERSATION)

    async def test_gate_provider_failure_is_silent_even_during_session(self):
        await self.voice.handle_microphone_transcript("Do you have Coke?")
        before = list(self.spoken)
        self.create.side_effect = RuntimeError("secret-provider-details")
        await self.voice.handle_microphone_transcript("How much?")
        self.assertEqual(self.spoken, before)
        self.assertEqual(self.agent.respond.await_count, 1)
        self.assertFalse(any(event.type == EventType.VOICE_ERROR for event in self.events))

    async def test_stop_prevents_late_classification_from_starting_speech(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def delayed(**kwargs):
            started.set()
            await release.wait()
            return model_result()
        self.create.side_effect = delayed
        task = asyncio.create_task(self.voice.handle_microphone_transcript("Do you have Coke?"))
        await started.wait()
        await self.voice.stop_all_audio()
        release.set()
        await task
        self.agent.respond.assert_not_called()
        self.assertEqual(self.spoken, [])

    async def test_background_vad_and_raw_transcript_do_not_refresh_session_or_emit_text(self):
        await self.voice.handle_microphone_transcript("Do you have Coke?")
        previous = self.gate.remaining
        async def capture(*args, on_activity, on_ready, **kwargs):
            self.now += 20
            on_activity()
            return "Did you finish the backend?"
        self.voice.audio.listen = AsyncMock(side_effect=capture)
        self.events.clear()
        self.assertEqual(await self.voice.listen_for_shopping(), "Did you finish the backend?")
        self.assertEqual(self.gate.remaining, previous - 20)
        self.assertEqual(self.events, [])
