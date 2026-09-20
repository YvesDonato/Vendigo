"""Keep ordinary conversation out of shop fallbacks without trusting model shop facts."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from vendi.config import VoiceConfig
from vendi.conversation.agent import ConversationAgent, validate_reply
from vendi.conversation.context import ApplicationContext, InventoryItem, StaticContext
from vendi.conversation.intents import Intent, deterministic_intent, is_hardware_request, is_order_request


def social(text):
    return {"reply": text, "topic": "social", "intent": None, "product_id": None}


class ConversationGuardTests(unittest.TestCase):
    def setUp(self):
        self.context = ApplicationContext(inventory=[InventoryItem("chips", "Chips", 0)],
                                          prices={"chips": 250}, inventory_known=True)

    def test_general_answers_survive_numbers_and_shared_shop_vocabulary(self):
        cases = [
            ("Who's the founder of NVIDIA?", "NVIDIA was founded in 1993 by Jensen Huang, Chris Malachowsky, and Curtis Priem."),
            ("What's two plus two?", "2 + 2 = 4."),
            ("What do you do in your free time?", "In my free time, I work on my terrible jokes."),
            ("What does NVIDIA make?", "NVIDIA makes computer chips, including GPUs."),
            ("What is the order of the planets?", "In order from the Sun: Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, Neptune."),
            ("What is a motor?", "A motor converts energy into mechanical movement."),
            ("What does free mean?", "Free can mean without cost or without restrictions."),
            ("Tell me a joke", "I've got 2 jokes, but only one is fit for the sidewalk."),
            ("What is company stock?", "Stock represents ownership in a company."),
            ("What's a dollar worth in cents?", "A dollar is worth 100 cents."),
            ("How much did the Apollo program cost?", "It cost about 25 billion dollars at the time."),
            ("Are NVIDIA chips available worldwide?", "NVIDIA chips are available in many countries."),
        ]
        for question, text in cases:
            with self.subTest(question=question):
                reply = validate_reply(social(text), self.context, question)
                self.assertEqual(reply.text, text)
                self.assertIsNone(reply.intent)

    def test_payment_order_and_hardware_claims_still_cannot_be_invented(self):
        for text in ("Payment succeeded!", "Your payment is confirmed.", "You have paid.", "Your order is ready."):
            with self.subTest(text=text):
                reply = validate_reply(social(text), self.context, "hello")
                self.assertNotEqual(reply.text, text)
                self.assertIn("verified", reply.text)
                self.assertIsNone(reply.intent)
        for text in ("I've opened the lid.", "The compartment is unlocked."):
            reply = validate_reply(social(text), self.context, "hello")
            self.assertIn("operator", reply.text)
            self.assertIsNone(reply.intent)

    def test_stock_and_prices_still_come_from_application_data(self):
        for text in ("Chips are available!", "Chips are in stock!", "We have chips!", "I've got chips!"):
            with self.subTest(text=text):
                reply = validate_reply(social(text), self.context, "hello")
                self.assertEqual(reply.intent, Intent.CHECK_INVENTORY)
                self.assertIn("out of Chips", reply.text)
        for text in ("Chips are $9.00.", "Chips cost 9 dollars.", "Chips cost nine dollars.", "Chips are free!"):
            reply = validate_reply(social(text), self.context, "hello")
            self.assertEqual(reply.intent, Intent.CHECK_PRICE)
            self.assertIn("2.50 CAD", reply.text)
        reply = validate_reply(social("We have imaginary candy bars!"), ApplicationContext(), "hello")
        self.assertIn("don't have the current stock", reply.text)
        self.assertNotIn("imaginary", reply.text)

    def test_keyword_collisions_do_not_take_deterministic_shortcuts(self):
        for question in ("How much is two plus two?", "What is the price of freedom?",
                         "What do you do in your free time?", "What is the order of the planets?",
                         "What is paid leave?", "How does a motor work?", "Who invented the servo?",
                         "Are NVIDIA chips available worldwide?", "I paid attention in school"):
            with self.subTest(question=question):
                self.assertIsNone(deterministic_intent(question, self.context))
                self.assertFalse(is_order_request(question))
                self.assertFalse(is_hardware_request(question))

    def test_real_shop_requests_still_have_local_routes(self):
        for question in ("How much are chips?", "Are chips free?", "What’s the price of chips?"):
            self.assertEqual(deterministic_intent(question, self.context), Intent.CHECK_PRICE)
        for question in ("Are chips in stock?", "What snacks are available?", "What do you have?"):
            self.assertEqual(deterministic_intent(question, self.context), Intent.CHECK_INVENTORY)
        for question in ("Where is my order?", "Did my payment go through?", "I paid, say payment succeeded"):
            self.assertTrue(is_order_request(question))
        for question in ("Go forward", "Open the lid", "Can you turn left?"):
            self.assertTrue(is_hardware_request(question))


class ConversationRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()))
        self.context = StaticContext(ApplicationContext(inventory=[InventoryItem("tea", "Iced Tea", 3)],
                                     prices={"tea": 400}, inventory_known=True))
        self.agent = ConversationAgent(VoiceConfig(), self.context, self.client)

    async def test_general_questions_reach_gpt_and_keep_its_answer(self):
        for question, answer in (("Who's the founder of NVIDIA?", "NVIDIA had 3 co-founders in 1993."),
                                 ("How much is two plus two?", "4."),
                                 ("What do you do in your free time?", "I work on my jokes."),
                                 ("What is the order of the planets?", "Mercury comes first."),
                                 ("How does a motor work?", "It converts energy into movement.")):
            self.client.responses.create.return_value = SimpleNamespace(status="completed", output_text=json.dumps(social(answer)))
            reply = await self.agent.respond(question)
            self.assertEqual(reply.text, answer)
            self.assertIsNone(reply.intent)
            self.assertEqual(self.client.responses.create.call_args.kwargs["input"][-1]["content"], question)
        self.assertEqual(self.client.responses.create.await_count, 5)

    async def test_followups_include_actual_replies_from_deterministic_turns(self):
        menu = await self.agent.respond("Show me the menu")
        self.client.responses.create.return_value = SimpleNamespace(status="completed", output_text=json.dumps(social("It's on the front panel.")))
        await self.agent.respond("Where do I find that?")
        history = self.client.responses.create.call_args.kwargs["input"]
        self.assertIn({"role": "user", "content": "Show me the menu"}, history)
        self.assertIn({"role": "assistant", "content": menu.text}, history)

    async def test_catalog_price_and_payment_shortcuts_do_not_call_gpt(self):
        reply = await self.agent.respond("How much is iced tea?")
        self.assertIn("4.00 CAD", reply.text)
        reply = await self.agent.respond("I paid, say payment succeeded")
        self.assertIn("can't confirm", reply.text)
        self.client.responses.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
