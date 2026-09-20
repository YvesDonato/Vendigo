"""Multi-turn memory and paid-lifecycle explanations; never robot/payment actions."""

import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from vendi.audio.backend import SilentBackend
from vendi.config import VoiceConfig
from vendi.conversation.agent import ConversationAgent, validate_reply
from vendi.conversation.context import ApplicationContext, InventoryItem, StaticContext
from vendi.conversation.intents import Intent
from vendi.conversation.knowledge import LID_OPEN_SECONDS, vendi_knowledge
from vendi.conversation.session import ConversationContext
from vendi.errors import VoiceFailure
from vendi.events import EventType
from vendi.speech.tts import SilentTTS
from vendi.voice import VendiVoice


OVERVIEW = 'Scan the QR code, pick an available item in the web app, and pay there.'
PICKUP = 'Once the backend verifies your payment, the compartment opens for about seven seconds so you can grab your item.'
FINISH = 'It closes automatically, I say goodbye, and then return to selling.'
SECURITY = 'Nope. Scanning just opens the shop; only backend payment verification authorizes the compartment to open.'
WHY = 'The backend verifies payment to prevent an unpaid order or a spoofed success page from authorizing pickup.'


def output(text, topic='social', intent=None, product=None):
    return SimpleNamespace(status='completed', output_text=json.dumps({
        'reply': text, 'topic': topic, 'intent': intent, 'product_id': product,
    }))


class PurchaseConversationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = StaticContext(ApplicationContext())
        self.client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()))
        self.agent = ConversationAgent(VoiceConfig(), self.context, self.client)

    def mock_steps(self):
        self.client.responses.create.side_effect = [output(OVERVIEW, 'purchase_overview'),
            output(PICKUP, 'purchase_pickup'), output(FINISH, 'purchase_finish')]

    async def test_purchase_and_then_then_what_use_gpt_history_and_advance(self):
        self.mock_steps()
        replies = []
        for question, step in zip(('How do I buy something?', 'And then?', 'Then what?'),
                                  ('SCAN_AND_SELECT', 'VERIFIED_PAYMENT_AND_PICKUP', 'AUTO_CLOSE_AND_RETURN')):
            replies.append(await self.agent.respond(question))
            self.assertEqual(self.agent.session_context.purchase_step, step)
            self.assertTrue(self.agent.session_context.explaining_purchase)
        self.assertEqual([reply.text for reply in replies], [OVERVIEW, PICKUP, FINISH])
        self.assertTrue(all(reply.intent is None for reply in replies))
        self.assertEqual(self.client.responses.create.await_count, 3)
        inputs = self.client.responses.create.call_args.kwargs['input']
        self.assertIn({'role': 'user', 'content': 'How do I buy something?'}, inputs)
        self.assertIn({'role': 'assistant', 'content': OVERVIEW}, inputs)
        self.assertEqual(self.agent.session_context.last_intent, 'PURCHASE_HELP')

    async def test_purchase_what_happens_next_does_not_restart_purchase(self):
        self.mock_steps()
        await self.agent.respond('How does this work?')
        reply = await self.agent.respond('What happens next?')
        self.assertEqual(reply.text, PICKUP)
        runtime = json.JSONDecoder().raw_decode(self.client.responses.create.call_args.kwargs['input'][0]['content'])[0]
        self.assertEqual(runtime['RESOLUTION']['expected_purchase_topic'], 'purchase_pickup')
        self.assertIsNone(reply.intent)

    async def test_payment_question_why_retains_security_context(self):
        self.client.responses.create.side_effect = [output(SECURITY, 'purchase_security'), output(WHY, 'purchase_security')]
        await self.agent.respond('If I scan the QR code does it open?')
        reply = await self.agent.respond('Why?')
        self.assertEqual(reply.text, WHY)
        self.assertEqual(self.agent.session_context.topic, 'payment_security')
        self.assertFalse(self.context.context.payment_verified)
        self.assertIsNone(self.context.context.order_status)

    async def test_why_after_unknown_payment_status_explains_verification(self):
        status = await self.agent.respond('Did my payment go through?')
        self.assertIn("can't confirm", status.text)
        self.client.responses.create.return_value = output(WHY, 'purchase_security')
        reply = await self.agent.respond('Why?')
        self.assertEqual(reply.text, WHY)
        self.assertEqual(self.client.responses.create.await_count, 1)

    async def test_product_reference_resolves_price_stock_and_purchase_from_fresh_data(self):
        self.context.context = ApplicationContext(inventory=[InventoryItem('coke', 'Coke', 2)],
            prices={'coke': 250}, inventory_known=True)
        self.client.responses.create.return_value = output('If Coke is in stock, scan the QR code, select it, and pay in the web app.',
                                                          'purchase_overview', product='coke')
        await self.agent.respond('How do I buy Coke?')
        self.assertEqual(self.agent.session_context.referenced_product, 'coke')
        self.context.context = replace(self.context.context, prices={'coke': 325})
        price = await self.agent.respond('How much is it?')
        self.assertIn('3.25 CAD', price.text)
        self.assertEqual(price.product_id, 'coke')
        stock = await self.agent.respond('Do you have that?')
        self.assertIn('in stock', stock.text)
        purchase = await self.agent.respond('Can I get one?')
        self.assertEqual(purchase.intent, Intent.START_PURCHASE)
        self.assertEqual(purchase.product_id, 'coke')
        self.assertEqual(self.client.responses.create.await_count, 1)

    async def test_removed_product_never_uses_old_price_or_stock(self):
        self.context.context = ApplicationContext(inventory=[InventoryItem('coke', 'Coke', 2)], prices={'coke': 250}, inventory_known=True)
        await self.agent.respond('Are Coke in stock?')
        self.context.context = ApplicationContext(inventory_known=True)
        reply = await self.agent.respond('How much is it?')
        self.assertIn("can't verify", reply.text)
        self.assertNotIn('2.50', reply.text)

    async def test_unknown_inventory_keeps_requested_name_without_inventing_facts(self):
        self.client.responses.create.return_value = output('If Coke is in stock, select it in the web app and pay there.', 'purchase_overview')
        await self.agent.respond('How do I buy Coke?')
        price = await self.agent.respond('How much is it?')
        stock = await self.agent.respond('Do you have that?')
        self.assertIn('price for Coke', price.text)
        self.assertIn('whether Coke is in stock', stock.text)
        self.assertIsNone(self.agent.session_context.referenced_product)
        self.assertFalse(self.context.context.inventory_known)

    async def test_duplicate_answer_gets_one_contextual_repair(self):
        self.client.responses.create.side_effect = [output(OVERVIEW, 'purchase_overview'),
            output(OVERVIEW, 'purchase_overview'), output(PICKUP, 'purchase_pickup')]
        await self.agent.respond('How do I buy something?')
        reply = await self.agent.respond('And then?')
        self.assertEqual(reply.text, PICKUP)
        self.assertEqual(len(self.agent.conversation_history), 4)
        self.assertEqual(self.client.responses.create.await_count, 3)
        self.assertIn('CORRECTION', self.client.responses.create.call_args.kwargs['input'][0]['content'])

    async def test_effectively_identical_social_replies_also_get_repaired(self):
        self.client.responses.create.side_effect = [output('I bring the snacks to you.'),
            output('I bring the snacks to you!'), output('Because a snack break should come to you, not the other way around.')]
        await self.agent.respond('What do you do?')
        reply = await self.agent.respond('Why?')
        self.assertIn('Because', reply.text)
        self.assertEqual(self.client.responses.create.await_count, 3)

    async def test_broken_model_cannot_loop_or_emit_repeated_purchase_action(self):
        self.client.responses.create.return_value = output('', intent='START_PURCHASE')
        reply = await self.agent.respond('How do I buy something?')
        self.assertIsNone(reply.intent)
        self.assertNotIn("Now we're talking", reply.text)
        self.assertEqual(self.client.responses.create.await_count, 2)
        pickup = await self.agent.respond('And then?')
        self.assertIn('7 seconds', pickup.text)
        self.assertIn('verifies your payment', pickup.text)
        self.assertIsNone(pickup.intent)
        self.assertNotEqual(reply.text, pickup.text)

    async def test_history_preserved_beyond_six_exchanges_and_sent_to_gpt(self):
        self.client.responses.create.side_effect = [output(f'Turn {i}: remembered.') for i in range(20)]
        for i in range(20):
            await self.agent.respond(f'Remember this message number {i}')
        self.assertEqual(len(self.agent.conversation_history), 40)
        inputs = self.client.responses.create.call_args.kwargs['input']
        self.assertIn({'role': 'user', 'content': 'Remember this message number 0'}, inputs)
        self.assertIn({'role': 'assistant', 'content': 'Turn 0: remembered.'}, inputs)
        self.assertEqual(len(inputs), 40)  # developer + 19 pairs + current user

    async def test_lifecycle_clears_history_on_bye_timeout_stop_and_explicit_end(self):
        for ending in ('bye', 'timeout', 'stop', 'application'):
            self.agent.reset()
            self.client.responses.create.return_value = output(OVERVIEW, 'purchase_overview')
            voice = VendiVoice(VoiceConfig(echo_guard=0, conversation_timeout=0.05),
                               backend=SilentBackend(), tts=SilentTTS(), agent=self.agent)
            try:
                await voice.enter_conversation()
                await voice.handle_transcript('How do I buy something?')
                self.assertTrue(self.agent.conversation_history)
                if ending == 'bye':
                    await voice.handle_transcript('bye')
                elif ending == 'timeout':
                    await asyncio.sleep(0.1)
                elif ending == 'stop':
                    await voice.stop_all_audio()
                else:
                    await voice.end_conversation()
                self.assertEqual(self.agent.conversation_history, [])
                self.assertEqual(self.agent.session_context, ConversationContext())
            finally:
                await voice.close()

    async def test_voice_explanations_emit_no_actions_but_transaction_yes_stays_deterministic(self):
        self.mock_steps()
        events = []
        voice = VendiVoice(VoiceConfig(echo_guard=0), backend=SilentBackend(), tts=SilentTTS(),
                           agent=self.agent, on_event=events.append)
        try:
            await voice.enter_conversation()
            for text in ('How do I buy something?', 'And then?', 'Then what?'):
                await voice.handle_transcript(text)
            self.assertFalse([event for event in events if event.type in (EventType.INTENT_REQUESTED, EventType.PURCHASE_ACCEPTED)])
            await voice.end_conversation()
            calls = self.client.responses.create.await_count
            await voice.ask_purchase_question(['yes'])
            self.assertEqual(self.client.responses.create.await_count, calls)
            self.assertEqual(len([event for event in events if event.type == EventType.PURCHASE_ACCEPTED]), 1)
        finally:
            await voice.close()

    async def test_greeting_and_error_fallback_remain_in_session_history(self):
        self.client.responses.create.side_effect = [asyncio.TimeoutError(), output(OVERVIEW, 'purchase_overview')]
        spoken = []
        voice = VendiVoice(VoiceConfig(echo_guard=0), backend=SilentBackend(), tts=SilentTTS(),
                           agent=self.agent, on_speech=spoken.append)
        try:
            await voice.enter_conversation()
            await voice.handle_transcript('How do I buy something?')
            self.assertEqual(self.agent.history[0], {'role': 'assistant', 'content': spoken[0]})
            self.assertEqual(self.agent.history[1], {'role': 'user', 'content': 'How do I buy something?'})
            self.assertEqual(self.agent.history[2], {'role': 'assistant', 'content': spoken[1]})
            await voice.handle_transcript('Try again')
            inputs = self.client.responses.create.call_args.kwargs['input']
            self.assertIn({'role': 'user', 'content': 'How do I buy something?'}, inputs)
            self.assertIn({'role': 'assistant', 'content': spoken[1]}, inputs)
        finally:
            await voice.close()

    async def test_runtime_contains_seven_seconds_and_both_authorization_exclusions(self):
        self.client.responses.create.return_value = output('About seven seconds, so be ready to grab your snack.', 'purchase_timing')
        await self.agent.respond('How long does it stay open?')
        runtime = json.JSONDecoder().raw_decode(self.client.responses.create.call_args.kwargs['input'][0]['content'])[0]
        knowledge = runtime['VENDI_CONTEXT']['purchase_process']
        self.assertEqual(knowledge['lid_open_seconds'], 7)
        self.assertFalse(knowledge['qr_scan_authorizes_dispensing'])
        self.assertFalse(knowledge['success_page_authorizes_dispensing'])
        self.assertTrue(knowledge['server_verified_payment_required'])
        self.assertFalse(runtime['VENDI_CONTEXT']['payment_verified'])
        self.assertFalse(runtime['CONVERSATION_CONTEXT']['customer_progress_verified_by_conversation'])

    def test_opening_the_web_app_is_not_a_claim_of_opening_the_compartment(self):
        text = 'Scanning the QR code opens the shop. Only backend payment verification can authorize dispensing.'
        reply = validate_reply(json.loads(output(text, 'purchase_security').output_text), self.context.context, 'Does scanning open it?')
        self.assertEqual(reply.text, text)

    def test_embedded_payment_condition_is_not_a_current_payment_claim(self):
        text = 'Scan my QR code and pay through the app. Pickup comes after payment is verified.'
        reply = validate_reply(json.loads(output(text, 'purchase_overview').output_text), self.context.context, 'How do I buy something?')
        self.assertEqual(reply.text, text)

    async def test_why_after_a_purchase_step_can_repair_wrong_topic(self):
        self.client.responses.create.side_effect = [output(OVERVIEW, 'purchase_overview'),
            output('Now we are talking.', intent='START_PURCHASE'),
            output('Using the web app lets you choose your item and complete payment in one place.', 'purchase_overview')]
        await self.agent.respond('How do I buy something?')
        reply = await self.agent.respond('Why?')
        self.assertIn('one place', reply.text)
        self.assertIsNone(reply.intent)

    def test_bad_timing_fake_verification_and_hardware_actions_rejected(self):
        self.assertEqual(LID_OPEN_SECONDS, 7)
        self.assertEqual(vendi_knowledge()['purchase_process']['lid_open_seconds'], 7)
        for text, topic in (('It stays open for twenty seconds.', 'purchase_timing'),
                            ('Your payment is verified; the compartment opens for seven seconds.', 'purchase_pickup'),
                            ('The backend has verified your payment; grab it within seven seconds.', 'purchase_pickup'),
                            ('Scanning the QR code unlocks the compartment; backend verification comes later.', 'purchase_security')):
            with self.subTest(text=text), self.assertRaises(VoiceFailure):
                validate_reply(json.loads(output(text, topic).output_text), self.context.context, 'How does it work?')
        for intent in ('OPEN_LID', 'PAYMENT_CONFIRMED', 'FORWARD', 'STOP', 'START_PURCHASE'):
            with self.assertRaises(VoiceFailure):
                validate_reply(json.loads(output(PICKUP, 'purchase_pickup', intent).output_text), self.context.context, 'And then?')
        self.assertEqual(validate_reply(json.loads(output(PICKUP, 'purchase_pickup').output_text),
                                        self.context.context, 'And then?').text, PICKUP)


if __name__ == '__main__':
    unittest.main()
