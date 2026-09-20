import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from vendi.config import VoiceConfig
from vendi.conversation.agent import ConversationAgent, validate_reply
from vendi.conversation.context import ApplicationContext, InventoryItem, StaticContext
from vendi.conversation.intents import Intent, render_intent
from vendi.errors import VoiceFailure


class AlternativeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = ApplicationContext(inventory=[
            InventoryItem('chips', 'Chips', 0), InventoryItem('kitkat', 'KitKat', 4),
            InventoryItem('water', 'Water', 2), InventoryItem('tea', 'Tea', 3),
        ], inventory_known=True)
        self.provider = StaticContext(self.context)
        self.client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=
            SimpleNamespace(status='completed', output_text=json.dumps({
                'reply': 'Invented alternative.', 'topic': 'social',
                'intent': 'CHECK_INVENTORY', 'product_id': None,
            })))))
        self.agent = ConversationAgent(VoiceConfig(), self.provider, self.client)

    async def test_absent_item_offers_exactly_two_real_alternatives(self):
        for question in ('Do you have pizza?', 'Can I get a sandwich?', 'Is ice cream available?'):
            reply = await self.agent.respond(question)
            self.assertEqual(reply.text, "Sorry, we don't have that in stock. But we do have KitKat and Water in stock.")
            self.assertEqual(reply.intent, Intent.CHECK_INVENTORY)
            self.assertIsNone(reply.product_id)

    async def test_sold_out_item_offers_two_without_changing_reference(self):
        reply = await self.agent.respond('Do you have chips?')
        self.assertIn('sold out', reply.text)
        self.assertIn('But we do have KitKat and Water in stock.', reply.text)
        self.assertEqual(reply.product_id, 'chips')
        self.client.responses.create.assert_not_called()

    async def test_alternatives_refresh_after_stock_changes(self):
        await self.agent.respond('Do you have pizza?')
        self.provider.context = ApplicationContext(inventory=[
            InventoryItem('kitkat', 'KitKat', 0), InventoryItem('water', 'Water', 0),
            InventoryItem('tea', 'Tea', 3),
        ], inventory_known=True)
        reply = await self.agent.respond('Do you have pizza?')
        self.assertEqual(reply.text, "Sorry, we don't have that in stock. But we do have Tea in stock.")
        self.provider.context = ApplicationContext(inventory=[], inventory_known=True)
        reply = await self.agent.respond('Do you have pizza?')
        self.assertEqual(reply.text, "Sorry, we don't have that in stock.")

    async def test_unknown_inventory_never_claims_absence_or_alternatives(self):
        self.provider.context = ApplicationContext(inventory=self.context.inventory, inventory_known=False)
        reply = await self.agent.respond('Do you have pizza?')
        self.assertIn("don't have the current stock list", reply.text)
        self.assertNotIn('KitKat', reply.text)
        self.provider.snapshot = AsyncMock(side_effect=VoiceFailure('context', 'offline'))
        reply = await self.agent.respond('Do you have pizza?')
        self.assertIn('trouble checking stock', reply.text)
        self.assertNotIn('KitKat', reply.text)

    async def test_general_menu_and_available_item_behaviour_is_unchanged(self):
        reply = await self.agent.respond('Do you have KitKat?')
        self.assertEqual(reply.text, 'KitKat is in stock—4 left.')
        reply = await self.agent.respond('What do you have?')
        self.assertIn("Right now I've got KitKat, Water, Tea.", reply.text)
        for question in ('Do you have any snacks?', 'What treats are available?', 'Can I get something to eat?'):
            reply = render_intent(Intent.CHECK_INVENTORY, self.context, transcript=question)
            self.assertNotIn("don't have that", reply.text)

    def test_model_alternatives_are_replaced_with_verified_stock(self):
        for text in ("We're out of pizza. We have Tea and imaginary candy!",
                     "Sorry, we don't have pizza in stock."):
            reply = validate_reply({'reply': text, 'topic': 'social', 'intent': None, 'product_id': None},
                                   self.context, 'Do you have pizza?')
            self.assertEqual(reply.text, "Sorry, we don't have that in stock. But we do have KitKat and Water in stock.")
